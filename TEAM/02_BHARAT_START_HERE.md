# Bharat — start here

> **SUPERSEDED — 4 Sep 19:00.** Read `TEAM/04_WEEKEND_HANDBOOK.html`
> instead. It has the same tasks with the current schedule and Ayush's
> work redistributed. This file is kept for its longer explanations.


You own the database and the index engine. Work in this order. Don't read ahead.

---

## Before anything: get the repo

```bash
git clone <the URL Mayank sends you>
cd apix
pip install sqlalchemy pyyaml pandas fastapi uvicorn httpx pytest numpy
```

Check it works:

```bash
python -m apix.cli bronze --stats
```

You should see ~2,700 simulated records across 91 days, **plus real
`cleartrip` records for 3 September**. Those real ones are the point — the
simulated history exists only so the chart has a shape behind them.

Look at one real record before you design anything:

```bash
python -c "from apix.collect import bronze; import datetime; r=[x for x in bronze.read_day(datetime.date(2026,9,3)) if x['source_id']=='cleartrip'][0]; print(r['route_code'], r['window_days'], r['fetch_status'], len(r['payload']), r['payload_sha256'][:16])"
```

Real payloads are ~1.8 MB each. That is the raw archive doing its job — do not
trim them.

---

## TASK 1 — Look at the data before you design for it (10 minutes)

Don't design a schema for data you haven't seen.

```bash
python -c "from apix.collect import bronze; import json,datetime; r=next(bronze.read_day(datetime.date(2026,9,1))); print(json.dumps(r, indent=2)[:1200])"
```

That's one Bronze record. **Every record has exactly these 14 keys**, always,
including the failures:

```
observation_date   route_code     window_days      departure_date
source_id          source_class   fetch_status     http_status
request_url        user_agent     payload          payload_sha256
error_detail       fetched_at_utc
```

`payload` is the raw response body as a string. On a failure it's `null` and
`fetch_status` tells you why. **You never modify these files. You only read them.**

---

## TASK 2 — Write `db/schema.sql` (60–90 minutes)

SQLite. Seven tables. Create the file `db/schema.sql`.

### The tables

**`bronze_observation_raw`** — one row per Bronze JSONL line. Same 14 columns
plus an `id INTEGER PRIMARY KEY`. Store `payload` as `TEXT`.

**`silver_fare_observation`** — one row per *flight quote*, so one Bronze
record with 6 quotes in it becomes 6 Silver rows.

```
id, bronze_id, observation_date, route_code, window_days, departure_date,
source_id, source_class, status, status_class,
carrier, flight_no, departure_time, stops,
base_fare, taxes, fees, total_fare, currency,
is_outlier, outlier_score, created_at
```

The unique constraint that makes re-running safe:

```sql
UNIQUE (observation_date, route_code, window_days, source_id,
        carrier, flight_no, total_fare)
```

**`gold_cell_median`** — one row per (route, window, day).
`observation_date, route_code, window_days, median_fare, n_used,
n_outliers_flagged, status, price_relative`

**`gold_route_index_daily`** — one row per (route, day).
`observation_date, route_code, route_index, n_windows_used, n_observations,
coverage, method_version, source_class`

**`gold_apix_daily`** — one row per day. This is the published number.
`observation_date, apix, change_pct, coverage, n_expected, n_observed,
confidence, weights_provisional, source_class, method_version, computed_at`

**`source_registry`** — load this from `compliance/verdicts/<date>.json`.
`source_id, source_name, kind, checked_on, verdict, reason, robots_sha256,
http_status, evidence_file`

**`ground_truth`** — load from `data/ground_truth.csv`.
`observation_date, route_code, window_days, departure_date, checker, website,
airline, flight_no, fare_shown, status, notes`

### The status column — do not invent values

Statuses come from `apix/vocab.py`. Seven of them, that's the whole list:

```
OK  SOLD_OUT  NO_SERVICE  SOURCE_DISALLOWED  FETCH_FAIL  BLOCKED  PARSE_FAIL
```

Add a `CHECK` constraint so the database itself refuses an eighth.

**There are no NULL statuses.** Every row has one. If you find yourself wanting
to leave one empty, the answer is one of the seven above.

### Done when

```bash
sqlite3 apix.db < db/schema.sql
```

runs clean, and you can insert one fake row into `silver_fare_observation`.

---

## TASK 3 — Write `db/schema.postgres.sql` (30 minutes)

**This is a presentation asset, not busywork.** A judge will ask why SQLite.
The answer is "SQLite is our demo profile, Postgres is the target, here is
the schema" — and then you show this file.

Same seven tables, but written the way you actually would for Postgres:

| SQLite | Postgres | Why |
|---|---|---|
| `payload TEXT` | `payload JSONB` + GIN index | queryable raw archive |
| `REAL` for money | `NUMERIC(10,2)` | floats lose paise |
| `TEXT` timestamps | `TIMESTAMPTZ` | real timezone handling |
| table name prefixes | `bronze.` `silver.` `gold.` schemas | actual namespacing |
| — | `CHECK (status IN (...))` | enforced vocabulary |

**Be able to say this out loud:** *"SQLite is the demo profile because it
installs nowhere and can't fail on stage. Postgres is the production target.
The application code doesn't change because it goes through SQLAlchemy — what
changes is JSONB for payloads, NUMERIC for money, TIMESTAMPTZ, and real
schemas instead of prefixes."*

---

## TASK 4 — The loader (90 minutes)

`apix/load/loader.py`. Reads Bronze files, writes Silver rows.

```python
from apix.collect import bronze
for rec in bronze.read_all():
    ...
```

For each Bronze record:

1. **If `fetch_status` is not `OK`** → write ONE Silver row carrying that
   status, with all the fare columns empty. The cell is still represented.
   This is how coverage stays honest.

2. **If `fetch_status` is `OK`** → parse the payload. **There are now TWO
   payload shapes**, so branch on `source_id`:

   ```python
   if rec["source_id"] == "cleartrip":
       from apix.collect.live_cleartrip import parse_quotes
       quotes = parse_quotes(rec["payload"])      # REAL fares
   else:
       quotes = json.loads(rec["payload"])["quotes"]   # replay, simulated
   ```

   **Do not write your own Cleartrip parser.** `parse_quotes()` already exists,
   is validated against the source (its minimum matches the cheapest fare the
   site itself displayed), and lives beside the adapter so there is one place
   to fix when the site changes.

   Both shapes return the same dict per quote:
   `carrier, flight_no, departure_time, stops, base_fare, taxes, fees,
   total_fare, currency`. Some fields are `None` for live data — Cleartrip's
   fare object does not carry a flight number. `None` is fine here; it is a
   missing *attribute*, not a missing observation, and the row still has a
   status of `OK`.

3. **If the payload won't parse, or has no usable quotes** → one row with
   status `PARSE_FAIL`.

4. **If `quotes` is an empty list** → one row with status `SOLD_OUT`.
   (Empty means the route ran but nothing was for sale.)

5. **Deduplicate** on the unique key above. Running the loader twice must
   produce the same row count. Use `INSERT OR IGNORE`.

6. **Outliers** — see Ayush's `METHODOLOGY.md`, section 5. Modified Z-score on
   MAD, threshold 3.5, computed *within* each (route, window, day) cell.
   **Set `is_outlier = 1`. Never delete the row.**

### Done when

```bash
python -m apix.load.loader        # run it
python -m apix.load.loader        # run it again
```

Row count is identical both times. If it isn't, your dedup key is wrong.

---

## TASK 5 — The index engine (2–3 hours) — your headline piece

`apix/index/engine.py`. Implement **exactly** what's in Ayush's
`METHODOLOGY.md`. Don't improvise a formula. If something in it looks wrong,
tell Ayush — don't quietly change it.

Order of operations:

1. Cell median → `gold_cell_median`
2. Price relative against the base → same table
3. Route index (geometric mean across windows) → `gold_route_index_daily`
4. National APIx (weighted sum across routes) → `gold_apix_daily`
5. Coverage and confidence **in the same pass**, not bolted on after
6. Carry `weights_provisional` onto every affected row

### The one test that matters

Build a tiny fixture — 2 routes, 2 windows, 3 fares each — and work out the
APIx **on paper**. Then check the engine reproduces your number. If it does,
your engine is right. If it doesn't, one of you is wrong and you need to know
which before 15:00 tomorrow.

---

## Four questions you must answer without notes

The jury will ask. Get these from Ayush and rehearse them:

1. Which index formula did you use, and what's it called?
2. Why the median and not the mean?
3. Why do windows combine geometrically but routes combine arithmetically?
4. What happens to the index when a source is blocked for two days?

"We invented one" is the wrong answer to question 1.

---

## If you get stuck

Message the group. Don't burn an hour silently — there are only 36.
