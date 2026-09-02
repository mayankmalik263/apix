# APIx — Internal Round 2 Plan

**Team TouchGrass.exe · SIH-UPES-2026-T020 · Problem SIH26056**
Written 2 September 2026, 01:00. Round 2 is 3–4 September.

---

## 1. The clock

We are planning against **3 September morning** as the hard deadline. If it
turns out to be the 4th, that is a bonus day, not a reason to add scope.

**Usable working time: roughly 24 hours, of which maybe 16 are productive.**

The presentation is **15 minutes**, and the shape of it decides everything below:

| Slot | Minutes | Owner |
|---|---|---|
| PPT | 4–5 | Bharat (problem, evidence, solution) |
| Prototype demo | 5 | Mayank |
| Jury questions | 5 | Whole team, Mayank + Bharat lead |

Rules from the meeting, treated as binding:

- **The prototype must be run at least 10 times before we present.** Not
  "should work". Ten actual runs, counted.
- **A copy of the PPT goes on a pendrive.**
- **Full run-throughs**, against a clock.
- **If a scenario is too complex to explain, cut it.** This is the single most
  useful instruction we got. It is the reason several things sit below the cut
  line in §8.

---

## 2. Three factual corrections that must reach the PPT

These are not opinions. They were checked against our own downloaded files
tonight. Two of them mean slides are currently wrong.

### 2.1 "India has no airfare index" — this is FALSE, and we were about to say it

MoSPI **does** publish an airfare-specific series:

> **"Air fare [normal]: economy class [adult]"**
> Weight **0.08** · Base 2012=100 · All-India Combined · Monthly
> Published in the CPI press-release **Annex-V**, "Year-on-year inflation rate
> of key items"

We recovered 12 monthly observations from the press releases already on disk.
Our extractor reproduces MoSPI's own published inflation rates to the decimal
(8.29 / 7.79 / 3.16 / 4.38 / 8.24 / 8.56), which is how we know the extraction
is right.

| | May | Jun | Jul | Sep | Oct | Nov |
|---|---|---|---|---|---|---|
| **2024** | 197.9 | 196.3 | 196.1 | 196.5 | 195.4 | 198.5 |
| **2025** | 214.3 | 211.6 | 202.3 | 205.1 | 211.4 | 215.5 |

**This is better for us, not worse.** The new argument:

> India measures every airfare in the country with **one number, at weight
> 0.08, national level only, once a month.** That number fell 4.4% in one
> month and its year-on-year rate swung from 3.16% to 8.56% inside five
> months. One monthly draw cannot describe a market that reprices every hour
> on 1,100 city pairs. We produce **30 route-level observations a day.**

That is a sharper pitch than "nothing exists", and it survives a MoSPI judge
who knows their own publications. The old version does not.

### 2.2 The state-level numbers in the build plan are unverified — do not use them

`apix-build-plan.html` §01 cites item code 294, COICOP 07.3.3.1.2.01, a
state-level spread of 376.09 points, Punjab 432.69, Andhra Pradesh 56.60,
Sikkim exactly 100.00, σ = 7.54%, and a −17.8% fall in March 2025.

**None of those numbers appear in any of our 491 downloaded CSVs.** The two
files that plan says are "already downloaded"
(`dgca_citypair_traffic_2015_2026.csv`, `mospi_cpi_airfare.json`) do not exist
anywhere on disk.

They may well be real and simply not downloaded yet. But until someone opens a
source and shows the figure, **they do not go on a slide and they do not go in
the demo script.** Use §2.1 instead — it is ours, it is verified, and we can
show the file it came from.

### 2.3 Route weights are not derived yet

Our six routes currently carry **equal weights**, because we do not have DGCA
city-pair passenger data. The code knows this: every index value it produces is
stamped `weights_provisional = true`.

Do not hand-type weights to make the flag disappear. Saying "our weights are
provisional pending DGCA traffic data, and the system marks every affected
value" is a *strength* in front of a statistical office. An invented weight
that a judge probes is fatal.

---

## 3. Ownership map

One rule: **you own an area, not a list of files.** If something in your area
is broken at 3am, it is yours regardless of who wrote it.

| Person | Owns | Presents |
|---|---|---|
| **Mayank** | Collection engine, API, dashboard, repo, demo packaging | Technical section + runs the demo |
| **Bharat** | Database, loader, index engine implementation | Problem, evidence, solution |
| **Ayush** | All mathematics and statistical justification | Backs Bharat on any formula question |
| **Kritika** | Ground truth: the human-verified fare panel | — |
| **Riya** | Ground truth + prior-art evidence | — |
| **Vidushi** | PPT, Q&A sheet, rehearsal discipline | — |

---

## 4. The interface contracts

These exist so nobody waits for anybody. Agree them now and no one is blocked
for the next 24 hours.

### 4.1 Mayank → Bharat: Bronze is a file, not a table

The collector writes newline-delimited JSON:

```
data/bronze/<observation_date>/<source_id>.jsonl
```

One line per cell. Every line has exactly these keys:

```json
{
  "observation_date": "2026-09-02",
  "route_code": "DEL-BOM",
  "window_days": 21,
  "departure_date": "2026-09-23",
  "source_id": "replay",
  "source_class": "SIMULATED",
  "fetch_status": "OK",
  "http_status": 200,
  "request_url": "...",
  "user_agent": "...",
  "payload": "<raw response body, verbatim>",
  "payload_sha256": "<64 hex chars>",
  "error_detail": null,
  "fetched_at_utc": "2026-09-02T14:30:00+00:00"
}
```

**Why files and not Bharat's database:**

- Mayank can collect before the database exists. Bharat can build the schema
  before the collector works. Neither blocks the other tonight.
- The raw archive survives the database being dropped and rebuilt — which it
  will be, several times, in the next 24 hours.
- When a jury asks "where is your raw data?", we open a file.

Bharat's loader reads these files. It never writes them.

### 4.2 Ayush → Bharat: the maths is a spec, not code

Ayush writes `METHODOLOGY.md` with the formulas and the *reason* for each
choice. Bharat implements exactly that. If Bharat needs to deviate, he asks
Ayush — he does not silently pick a different formula.

### 4.3 Bharat → Mayank: the API reads Gold

Mayank's FastAPI layer queries Bharat's `gold_*` tables. Agreed shape:

```
gold_apix_daily(observation_date, apix, change_pct, coverage,
                n_expected, n_observed, confidence,
                weights_provisional, source_class, method_version)
```

If Bharat changes a column name, he tells Mayank in the group **immediately**.
A renamed column at 4am is a dead demo.

### 4.4 Status vocabulary is frozen

`apix/vocab.py` is already committed and is the contract. Seven statuses, three
classes. **Nobody adds an eighth.** If you think you need one, it is a bug in
your parsing, not a gap in the vocabulary.

---

## 5. Database decision — SQLite now, Postgres on paper

**We build and demo on SQLite.** Reason, stated plainly: Docker is not
installed on the build machine, and neither is WSL2. Installing both means two
reboots and a BIOS virtualisation check, 24 hours before a demo that must run
ten times. That is not a risk worth taking for zero marks.

**Bharat also commits `db/schema.postgres.sql`** — the same tables written
properly for PostgreSQL, using the features SQLite does not have:

- `JSONB` for the raw payload, with a GIN index
- `NUMERIC(10,2)` for money instead of SQLite's float
- `TIMESTAMPTZ` instead of naive datetimes
- real `CHECK` constraints on the status vocabulary
- proper schemas (`bronze.`, `silver.`, `gold.`) instead of name prefixes

That file is not decoration. It is the answer to *"why SQLite?"*:

> SQLite is our demo profile because it installs nowhere and cannot fail on
> stage. Postgres is the production target — here is the schema, and here is
> what changes: JSONB for raw payloads, NUMERIC for money, TIMESTAMPTZ,
> and real schemas instead of prefixes. The application code is unchanged
> because it goes through SQLAlchemy.

That answer scores. "We used SQLite because it was easy" does not.

---

## 6. Per-person tasks

### MAYANK — collection engine, API, dashboard, repo

You own the demo. If it fails on stage, it is yours.

**Block A (2h) — Bronze writer + CLI**
- [ ] `apix/collect/bronze.py` — writes the JSONL format in §4.1
- [ ] `apix/collect/runner.py` — loops 6 routes × 5 windows, writes every
      outcome including failures, refuses uncleared sources via the gate
- [ ] `apix/cli.py` — `collect`, `compliance`, `seed`, `serve` as real
      subcommands
- **Done when:** `python -m apix.cli seed --days 90` produces 90 folders of
  JSONL and `python -m apix.cli compliance --report` prints the 11-row table

**Block B (2h) — API**
- [ ] FastAPI reading Bharat's Gold tables
- [ ] `/v1/apix/series`, `/v1/apix/latest`, `/v1/routes/{code}/series`,
      `/v1/windows/{days}/series`, `/v1/compliance/report`, `/v1/methodology`
- [ ] `/v1/lineage/{date}/{route}/{window}` — walks Gold → Silver → the Bronze
      file and returns the payload hash. **Build this before anything pretty.**
      It is the auditability claim.
- **Done when:** `/docs` renders and every endpoint returns real data

**Block C (3h) — Dashboard**
- [ ] The money chart: APIx daily line over the real MoSPI monthly series as a
      step line. **If only one chart exists, it is this one.**
- [ ] Headline strip: today's APIx, day-on-day change, coverage %, confidence
      grade
- [ ] Booking-window curve — five windows on one axis, the thing no official
      index publishes
- [ ] Simulated series drawn visibly differently, with a legend entry saying so
- **Done when:** it opens with the API down and still shows something sensible

**Block D (2h) — Demo packaging**
- [ ] One command from cold clone to running dashboard
- [ ] Run it 10 times. Count them. Write the count down.
- [ ] Record a 90-second screen capture as insurance
- [ ] README with the compliance table and a screenshot

**Also yours:** the git history. Commit per feature, with a message that says
*why*. Bharat and you both push to `main` — small commits, pull before you push.

---

### BHARAT — database, loader, index engine

You own the number. When a judge asks "how is the index computed", you answer.

**Block A (2h) — Schema**
- [ ] `db/schema.sql` — SQLite, the tables we actually run on
- [ ] `db/schema.postgres.sql` — the Postgres version per §5. This is a
      **presentation asset**, write it properly.
- [ ] Tables: `bronze_observation_raw`, `silver_fare_observation`,
      `gold_cell_median`, `gold_route_index_daily`, `gold_apix_daily`,
      `source_registry`, `ground_truth`
- **Done when:** the schema applies clean and you can insert one fake row

**Block B (3h) — Loader, Bronze → Silver**
- [ ] Read Mayank's JSONL files (§4.1). Never modify them.
- [ ] Parse into base fare / taxes / fees / total, attach carrier and flight no
- [ ] Assign a status from `apix/vocab.py` to **every** row — no NULLs
- [ ] Deduplicate on `(observation_date, route, window, source, carrier,
      flight_no, total_fare)`
- [ ] Flag outliers with the method Ayush specifies. **Flag, never delete.**
- **Done when:** running the loader twice gives an identical row count

**Block C (4h) — Index engine — your headline piece**
- [ ] Implement exactly what Ayush wrote in `METHODOLOGY.md`
- [ ] Store `method_version` on every Gold row
- [ ] Compute coverage and confidence in the same pass, not as decoration
- [ ] Propagate `weights_provisional` onto every affected row
- [ ] **The test that matters:** a small fixture whose APIx you worked out on
      paper. If the engine reproduces your hand calculation, it is right.
- **Done when:** `gold_apix_daily` has 90 rows and at least one B or C grade

**What you must be able to say out loud, without notes:**
- Which index formula you used and why
- Why the median and not the mean
- Why windows combine geometrically and routes combine arithmetically
- What happens to the index when a source is blocked for two days

---

### AYUSH — the mathematics

No coding required beyond checking Bharat's numbers, but **nothing Bharat
builds is defensible without you.**

**Block A (2h) — `METHODOLOGY.md` v0.1.** The whole spec, with subscripts:
- [ ] Cell median: `P(r,w,t) = median{ total_fare : status=OK, not outlier }`
- [ ] Price relative: `R(r,w,t) = P(r,w,t) / P(r,w,0)`, base = mean of first 7
      daily medians, base period = 100
- [ ] Route index: geometric mean across the 5 windows — **name it: this is a
      Jevons index**, and it is what CPI elementary aggregation uses
- [ ] National index: `APIx(t) = Σ ω_r · I(r,t)` with fixed weights —
      **name it: Laspeyres-type**, revised annually not daily
- [ ] Coverage and the A/B/C confidence thresholds
- [ ] Outlier rule: modified Z-score on MAD, threshold 3.5, per cell —
      say whose method it is (Iglewicz & Hoaglin) and why not mean±3σ

**Block B (2h) — Written justifications.** One short paragraph each, plain
English, because these are jury answers not footnotes:
- [ ] Why median, not mean — fare distributions are right-skewed
- [ ] Why geometric across windows, arithmetic across routes
- [ ] Why 7 days of base and what happens before day 7
- [ ] Why no machine learning — we measure, we do not predict

**Block C (if time) — Weights.** Find DGCA city-pair passenger numbers and
derive the six weights. If you cannot find them in 90 minutes, **stop** — the
provisional-weights flag is a perfectly good answer and is already built.

**Block D — Verify Bharat.** Recompute one day's APIx by hand from the Silver
rows. If your number and the engine's number differ, that is the most
important bug in the project.

---

### KRITIKA — ground truth lead

You produce the evidence that our program tells the truth. **This is the single
highest-credibility item any non-coder can create, and it takes one session.**

**Today (2h) — the validation panel**
- [ ] Price **all 30 cells by hand**: 6 routes × 5 windows
      (T+1, T+7, T+14, T+21, T+45)
- [ ] Split with Riya and Vidushi — 2 routes each, 10 cells each
- [ ] Columns exactly:
      `date_checked, time, route, window_days, departure_date, airline,
      flight_no, fare_shown, website, status, notes`
- [ ] `status` uses our vocabulary: `OK`, `SOLD_OUT`, or `NO_SERVICE`.
      **Never leave a cell blank** — if there is no flight, that is
      `NO_SERVICE` and it is information.
- [ ] Save as `data/ground_truth.csv` and send it to Mayank

**Departure dates from 2 September:** T+1 → 3 Sep · T+7 → 9 Sep ·
T+14 → 16 Sep · T+21 → 23 Sep · T+45 → 17 Oct

**Then:** chase Riya and Vidushi until all 30 rows exist. That chasing is the
job, not an extra.

**Why this matters more than it looks:** it converts "we scraped some numbers"
into "we validated against 30 independently human-verified fares." One line in
the demo. Disproportionate credibility.

---

### RIYA — ground truth + prior art

**Block A (1h):** your 10 cells of the manual panel, with Kritika.

**Block B (2h) — the "why is this new" evidence.** The jury will ask how we
differ from what exists. Answer it with sources, one page:

- [ ] **US:** Bureau of Labor Statistics publishes CPI "Airline fares", series
      `CUUR0000SETG01`, monthly, public API at api.bls.gov. Confirm it is
      monthly and **not route-level**.
- [ ] **Europe:** Eurostat HICP `CP0733` "Passenger transport by air", dataset
      `prc_hicp_midx`, monthly. Confirm **not route-level**.
- [ ] **India:** the MoSPI Air fare item in §2.1 — weight 0.08, monthly,
      national only.
- [ ] Any commercial product (IATA, airline analytics) — what it costs, who
      can access it.

**The sentence we want to be able to say:** *"No index anywhere publishes
airfares daily at route level, and India's only airfare number is a single
monthly national figure at weight 0.08."* Your page is what makes that sayable.

---

### VIDUSHI — PPT, Q&A, rehearsal

You own everything the judges read and hear. The deck is currently built for a
different format and contains a claim we now know is wrong.

**Block A (2h) — cut the deck to 4–5 minutes**
- [ ] **Fix the airfare claim** using §2.1. Anywhere the deck says India has no
      airfare index, it must now say India has *one national monthly number at
      weight 0.08*.
- [ ] **Remove the state-level statistics** from §2.2 entirely until someone
      produces the source file.
- [ ] Time it out loud. 4–5 minutes is roughly 550–700 spoken words. Cut until
      it fits. Do not speak faster.
- [ ] Bell MT, every text box ending above 6.7", never touch slides 1 and 2.
- [ ] **Export a PDF as well as the PPTX. Both on the pendrive.**

**Block B (1h) — the Q&A sheet.** One page, one line per answer, printed:
- Which index formula? *(from Ayush)*
- Why median not mean? *(from Ayush)*
- Where is the AI? *"There is none, deliberately. This measures, it does not
  predict. A model makes the number harder to audit."*
- The PS asks for CAPTCHA handling and IP rotation — where is it?
  *"Deliberately absent. The same statement requires robots.txt compliance;
  both cannot hold. Sources that refuse are logged and reported as a finding."*
- How much of this is real? *"MoSPI overlay real. Compliance checks real, run
  today. Today's collection real. The 90-day history is simulated from a
  documented model and labelled SIMULATED in the database."*

**Block C — rehearsal discipline. Nobody else owns this.**
- [ ] Hold the clock for the 10 prototype runs. Write down how many actually
      succeeded.
- [ ] Time Bharat's 4–5 minutes. Time Mayank's 5 minutes.
- [ ] Full run-through, twice, end to end.
- [ ] **Apply the meeting rule:** anything Bharat or Mayank cannot explain in
      one clean sentence gets cut from the script. You make that call.

---

## 7. Schedule

Times are from now (2 Sep, 01:00). Everything before the line must be true.

| Hours | Mayank | Bharat | Ayush | K / R / V |
|---|---|---|---|---|
| 0–2 | Bronze writer + CLI | Schema (both files) | METHODOLOGY.md | Manual panel, all 30 cells |
| 2–5 | Seed 90 days → JSONL | Loader, Bronze→Silver | Justification paragraphs | PPT cut + prior-art page |
| 5–9 | FastAPI + lineage | **Index engine** | Verify Bharat by hand | Q&A sheet |
| 9–12 | Dashboard, money chart first | Backfill Gold, coverage | Weights, if findable | Rehearsal 1 |
| 12–16 | Integration + validation table | Fix what integration breaks | — | Rehearsal 2 |
| 16–20 | **Freeze.** 10 runs. Screen capture. | Support | — | Time the run-throughs |

**The freeze is real.** After hour 16, no new features. Only fixes to things
that break during the 10 runs.

---

## 8. The cut line

Decide now, while it is cheap. When we run late — and we will — cut from the
bottom without a discussion.

| Item | Call | Why |
|---|---|---|
| Compliance gate with dated evidence | **MUST** | Answers the hardest question in the PS. Already built. |
| Bronze → Silver → Gold with real lineage | **MUST** | The auditability claim collapses without it |
| Index engine + method version + confidence | **MUST** | Separates an index from a scraper |
| APIx vs MoSPI overlay chart | **MUST** | The single frame that carries the pitch |
| One genuinely live fare from a permitted source | **MUST** | Proves the pipeline touches reality once |
| Manual ground-truth validation table | **SHOULD** | 2 hours of non-coder time for large credibility |
| Booking-window curve | **SHOULD** | Strong, and unique to us |
| Lineage drill-down in the UI | **SHOULD** | The API endpoint alone can carry it |
| Route heatmap | **COULD** | Cut first |
| A second and third live source | **WON'T** | The adapter pattern shows extensibility once |
| Docker, Postgres running, CI, auth | **WON'T** | Zero marks. The schema file is the story. |
| Forecasting or ML | **WON'T** | Actively harmful — MoSPI wants measurement |
| Anti-bot work of any kind | **WON'T** | Contradicts our entire position |

---

## 9. Constraints and risks, stated honestly

| Risk | Likelihood | What we do |
|---|---|---|
| Live portal blocks us during the demo | High | Live attempt falls back to cached data and *prints why*. The fallback demonstrates the status vocabulary — it is a feature, not a save. |
| Bharat's schema and Mayank's collector diverge | Medium | §4.1 is frozen. Any change is announced in the group before it is committed. |
| Index engine not finished by hour 9 | Medium | Dashboard reads whatever Gold rows exist; an incomplete series still renders. Never let the chart depend on a complete backfill. |
| Only ~1 day of manual ground truth | Certain | Say so. "30 human-verified fares from one day" is honest and still strong. Do not imply more. |
| Someone asks for the state-level CPI numbers | Medium | We do not present them. See §2.2. |
| Demo machine differs from build machine | Medium | SQLite + static dashboard + no Docker means the whole thing is a folder copy. |
| We over-explain and run out of time | **High** | Vidushi cuts anything that needs more than one sentence. This is the meeting's own rule. |

**The honest limitation to volunteer before a judge finds it:** we have one day
of real collection and a 90-day simulated history. We say that out loud, we
label it in the database, and we draw it differently on the chart. A prototype
with honest labels beats one with an impressive unlabelled backfill, every
time.

---

## 10. Git workflow

Repo lives at `D:\SIH 2k26\apix`. Mayank creates the GitHub remote and invites
everyone.

- `main` only. We do not have time for branch review.
- **Pull before you push. Every time.**
- One commit per working thing, not one commit per session.
- Commit message says *why*, not what. `fix: median was including outliers`
  beats `updated engine.py`.
- **Never commit:** the `.db` file, `node_modules/`, `data/bronze/`.
  Already in `.gitignore`.
- If you break `main`, say so in the group immediately. Do not quietly fix it
  at 4am.

---

## 11. The 5-minute demo runbook

Rehearse this exact path. Nothing else.

| Time | What | Say |
|---|---|---|
| 0:00 | MoSPI airfare series on screen | "India measures every airfare with one monthly national number, weight 0.08. It moved 4.4% in a month." |
| 0:45 | Run the compliance gate | "Six sources cleared today, five refused by name. The refusal is the feature — we do not defeat blocks." |
| 1:30 | Run the collector | "Thirty cells. Every outcome recorded, including the failures." |
| 2:15 | Follow one fare through the layers | "Raw payload with its hash, then the parsed row, then the index cell. Every published number walks back to bytes we kept." |
| 3:15 | The overlay chart | "Our daily line against MoSPI's monthly steps." Then the booking-window curve: "no index anywhere publishes this." |
| 4:15 | Coverage and confidence | Name the simulated series *before* anyone asks. Show the ground-truth table. |
| 4:45 | Close | "Six routes, five windows, 150 observations per route per month against the official one. Adding a route is a config line." |

**If something fails on stage:** say what failed, point at the status it
produced, and carry on. A `BLOCKED` row appearing live is the system working as
designed. Do not apologise for it and do not try to fix it in front of them.

---

## 12. Definition of done for Round 2

We are ready when all of these are true:

- [ ] The prototype has been run **10 times** and someone wrote down the count
- [ ] The PPT is 4–5 minutes **timed out loud**, and the wrong airfare claim is fixed
- [ ] PPTX **and** PDF are on a pendrive
- [ ] A 90-second screen recording exists as demo insurance
- [ ] Bharat can state the index formula without notes
- [ ] Ayush has verified one day's APIx by hand and it matches the engine
- [ ] 30 manual ground-truth fares exist in `data/ground_truth.csv`
- [ ] The Q&A sheet is printed
- [ ] Two full run-throughs are done against a clock
