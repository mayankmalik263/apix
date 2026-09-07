# APIx — India's daily airfare price index

**SIH26056 · MoSPI, Data Informatics & Innovation Division · Team TouchGrass.exe**

India measures every airfare in the country with **one number, once a month**:
the CPI item *"Air fare [normal]: economy class [adult]"*, weight 0.08,
All-India combined. Airfares on any of ~1,100 domestic city pairs can move
several hundred percent inside a day.

APIx measures **30 prices a day** instead — 6 routes × 5 booking windows — and
turns them into a daily index built the way a CPI elementary aggregate is
built, with coverage, a confidence grade and a provenance path attached to
every published value.

This is not a fare scraper. It is a measuring instrument that reads prices off
the web.

---

## Run it

```bash
pip install -r requirements.txt
python -m playwright install chromium
python -m apix.cli demo
```

That single command runs the whole thing: checks compliance, collects one live
cell from a permitted source, parses the raw archive into the clean table,
computes the index, and serves the dashboard at <http://localhost:8000/>.

It is built to be watched. Every failure is narrated rather than hidden — if a
portal blocks us on stage, the run says so, records a `BLOCKED` row, and keeps
going. That is the system working as designed.

```bash
python -m apix.cli demo --offline      # no network at all; runs off the archive
python -m apix.cli demo --no-serve     # stop before starting the server
```

---

## Three tiers of access

| | | |
|---|---|---|
| `/` and `/public/*` | **open**, rate limited | The dashboard. A statistical office publishes its numbers; putting a login in front of a published series would be theatre. |
| `/v1/*` | **API key** | The documented integration surface for the RBI and the NSO. The key is not there to keep them out — it makes bulk access attributable, rate-limitable and revocable, and lets us answer "who read what, when". |
| `/admin` | **operator session** | Issuing keys, forcing a collection, reading the access log. There is no signup page: accounts are made from a shell with `apix useradd`. |

Keys carry scopes (`read:index`, `read:lineage`, `read:compliance`), enforced at
the `/v1` boundary — advertising a scope and then not checking it would be worse
than having none, because it would look like access control while being
decoration.

A key is shown exactly once, at creation. Only a SHA-256 of it is stored, so
nobody — including us — can recover it later; a lost key is rotated, not
retrieved. Passwords use scrypt with a per-user salt, sign-in failures are
indistinguishable between "no such account" and "wrong password", and five
failures lock the account for fifteen minutes.

---

## The daily schedule

APScheduler runs inside the app and collects at the slot declared in
`config/basket.yml` (20:00 IST). The slot is **fixed on purpose**: fares move
through the day, so a series collected at 09:00 on Monday and 21:00 on Tuesday
would measure the clock as much as the price.

What is optimised is everything around that moment — a catch-up run if the
machine was asleep at the slot, resumption of only the cells that failed rather
than the whole grid, and rate limiting that respects each source's declared
crawl delay.

Every run is written to `collection_run` *before* it starts, so a run that
crashes halfway leaves evidence. A day with no row at all means the scheduler
never fired, which is a different failure from a day that fired and collected
nothing — and the two must never look the same.

---

## On Scrapling

The collector uses [Scrapling](https://github.com/D4Vinci/Scrapling) as a
**parser**: `apix/collect/adaptive.py` uses its `Selector` to re-find fare
elements by shape and context when a literal CSS selector stops matching. That
directly answers a named risk in the problem statement — "page-structure changes
silently breaking the parser" — and `tests/test_adaptive.py` proves it by
renaming every class on the page and checking we still recover the fares, and
that the result reports *how* it recovered rather than passing a fallback off as
a healthy parse.

We deliberately do **not** use Scrapling's `Fetcher`, `DynamicFetcher` or
`StealthyFetcher`. Those depend on `curl_cffi`, which impersonates a browser's
TLS fingerprint, and `patchright`, a Playwright fork built to defeat bot
detection. Neither is installed. Fetching stays on plain Playwright with the
identifiable user agent from `compliance/registry.yml`.

APIx does not evade detection. That position is the project, and a dependency is
not a loophole in it.

---

## What it does, in five steps

| | | |
|---|---|---|
| **1** | **The gate** | Fetch each source's `robots.txt`, hash it, date it. Refuse anything not cleared *today* — before the browser is even launched. |
| **2** | **Collect** | 30 cells, rate-limited, from permitted sources only. Every outcome written, including the failures. |
| **3** | **Bronze** | The raw response, verbatim, with its SHA-256. Append-only. Never edited. |
| **4** | **Silver** | One row per fare quote, each carrying a status from a frozen seven-value vocabulary. |
| **5** | **Gold** | Cell median → price relative → route index (geometric) → APIx (weighted arithmetic), with coverage and confidence computed in the same pass. |

```
bronze_observation_raw  →  silver_fare_observation  →  gold_cell_median
                        →  gold_route_index_daily   →  gold_apix_daily
```

Any published number walks back down that chain to the bytes it came from:

```bash
curl localhost:8000/v1/lineage/2026-09-07/DEL-BOM/21
```

---

## A missing price is never just missing

This is the idea the project is built on. A sold-out flight and a crashed
scraper both look like a blank cell — one is a fact about the market, the other
is a fact about us. Collapse both into `NULL` and you can never tell them apart
again, and you lose the ability to report honestly on your own coverage.

| Status | Class | In the price? | Counts as observed? |
|---|---|---|---|
| `OK` | MARKET | yes | yes |
| `SOLD_OUT` | MARKET | no | **yes** — we checked, and the market answered |
| `NO_SERVICE` | MARKET | no | removed from the denominator |
| `SOURCE_DISALLOWED` | POLICY | no | no — a gap we chose, reported not hidden |
| `FETCH_FAIL` · `BLOCKED` · `PARSE_FAIL` | SYSTEM | no | no — our failure, counted against us |

The database itself refuses an eighth value.

---

## Compliance

The problem statement asks for CAPTCHA handling and IP rotation **and** for
robots.txt and terms-of-service compliance. Both cannot hold at once. We built
the permission-tiered version, and we report the sources that refuse us as a
finding about market observability rather than an obstacle to defeat.

There is no CAPTCHA handling and no IP rotation anywhere in this codebase.
`compliance/registry.yml` carries `bypass_captcha: false` and `rotate_ip: false`
as settings that are present so a reader can see they are never flipped.

```bash
python -m apix.cli compliance --check      # re-fetch every robots.txt
python -m apix.cli compliance --report     # print the 11-source table
```

Verdicts are written to `compliance/verdicts/<date>.json` and the robots.txt
bodies to `compliance/evidence/`, hashed. Deliberately files, not database rows:
the compliance trail must survive the database being dropped and rebuilt.

**Six of eleven sources currently permit collection.** The other five could not
be verified — read timeouts, which is *not* proof of a bot wall, and is recorded
as exactly that rather than overstated.

---

## The maths

Specified in [`METHODOLOGY.md`](METHODOLOGY.md), implemented in
`apix/index/engine.py`, and pinned by a hand calculation in `tests/`.

```
P(r,w,t) = median of OK fares in the cell            cell median
R(r,w,t) = P(r,w,t) / P(r,w,0)                       price relative
I(r,t)   = 100 × (Π R)^(1/W)                         route index — Jevons
APIx(t)  = Σ ω_r · I(r,t),  Σ ω_r = 1                Laspeyres-type
```

Windows combine **geometrically** because they are ratios and ratios multiply;
a doubling and a halving cancel to exactly 100, where a plain average would say
125. Routes combine **arithmetically** because each carries a real share of what
travellers spend, like items in a household budget.

Route weights are currently equal and every affected row is stamped
`weights_provisional = 1`, pending DGCA city-pair passenger data. Do not
hand-type weights to make that flag go away.

```bash
python -m pytest tests/ -v          # 53 tests
python scripts/dry_run.py           # 10 counted cold starts -> data/dry_run_log.md
```

`dry_run.py` is the meeting's "ten actual runs, counted" made into a file. Each
run deletes a scratch database, reapplies both schemas, reparses the whole raw
archive, recomputes the index, boots the API, serves every page, calls every
open endpoint, walks the lineage back to a real SHA-256, and checks that the
keyed API and the admin console **refuse** an anonymous caller.

The test that matters reproduces an index worked out on paper:
`100 × √(1.10 × 0.90) = 99.498744`, and the engine has to agree.

---

## Why SQLite

SQLite is the demo profile because it installs nowhere and cannot fail on
stage. PostgreSQL is the production target and
[`db/schema.postgres.sql`](db/schema.postgres.sql) is what that costs: `JSONB`
with a GIN index for the raw archive, `NUMERIC(10,2)` for money instead of a
float that loses paise, `TIMESTAMPTZ`, the status vocabulary as a declared
`ENUM` instead of a `CHECK` list copied into four tables, monthly range
partitions on Bronze, and real `bronze.` / `silver.` / `gold.` schemas so an
NSO read-only role can be granted the published index without the raw archive.

The application code does not change — it goes through SQLAlchemy.

---

## API

```
GET /v1/apix/latest           today's number, with everything that qualifies it
GET /v1/apix/series           the daily series (source_class = LIVE | SIMULATED | all)
GET /v1/routes/{code}/series  one route over time
GET /v1/windows/{days}/series one booking window — the lead-time curve
GET /v1/windows/curve         median fare by window for one day
GET /v1/compliance/report     which sources we were permitted to collect from
GET /v1/bronze/stats          what is in the raw archive
GET /v1/lineage/{date}/{route}/{window}    gold → silver → bronze + sha256
GET /v1/methodology           the methodology document itself
GET /v1/basket                routes, windows and weights
GET /v1/mospi                 MoSPI's own published airfare item index
GET /v1/health
GET /v1/system/status         server clock, next collection, archive counts
```

Authenticate either way — a consumer should not have to guess:

```bash
curl -H "Authorization: Bearer apix_live_..." localhost:8000/v1/apix/latest
curl -H "X-API-Key: apix_live_..."            localhost:8000/v1/apix/series
```

Interactive docs, generated by FastAPI, at `/docs`.

---

## Real and simulated never mix

The prototype ships with a labelled 91-day synthetic history so the chart has a
shape behind the real days. Every row of it is stamped `SIMULATED` and there is
no flag to turn that off. It is drawn dashed, the legend says so, and it is
based separately — **nothing real is ever computed from a simulated number.**
`source_class` is part of the key on all three Gold tables so the database
enforces that rather than trusting a query to remember it.

```bash
python -m apix.cli seed --days 91     # regenerate it; deterministic, seed 26056
```

---

## Stated limitations

Said here so nobody has to find them.

1. Real collection began 3 September 2026. Everything before that is simulated.
2. Weights are provisional — equal, pending DGCA city-pair data.
3. Single-day base in v0.1; becomes a 7-day mean at v0.2.
4. Six routes of roughly 1,100 city pairs. Five observations a day per route is
   ~150 a month, against the official one.
5. Five of eleven named sources could not be checked.
6. The daily series carries a day-of-week cycle we have not yet removed — see
   METHODOLOGY §11.
7. The live source returns multiple fare products per itinerary. v0.1 keeps
   every quote as a distinct observation and does not yet separate fare
   families; a deduplication policy needs to be agreed, not invented.

---

## Layout

```
apix/
├─ collect/     the gate, the adapters, the Bronze archive
├─ load/        Bronze → Silver, plus the compliance and ground-truth tables
├─ index/       the index engine
├─ api/         FastAPI: the public and keyed tiers
├─ web/         auth, API keys, the scheduler, the stats aggregation
└─ vocab.py     the seven statuses — frozen
config/basket.yml      routes, windows, weights — configuration, not code
compliance/            registry, dated verdicts, hashed robots.txt evidence
db/                    SQLite schema, the web-layer schema, the PostgreSQL target
dashboard/             index, login, admin console, API docs — ECharts vendored
                       locally, so it works with the wifi off
tests/                 the hand calculation and the claims we make out loud
```
# SIH_apix
