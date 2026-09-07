# APIx — full context handoff

Paste this whole file as the first message in a new chat. It replaces the
conversation it came from. Written 8 September 2026.

---

## 1. WHO

**Team TouchGrass.exe** · SIH-UPES-2026-T020 · UPES Dehradun
Lead: **Mayank Malik**, SAP 590013857, mayankmalik.13857@stu.upes.ac.in

| Person | Status | Role |
|---|---|---|
| Mayank | active | Lead. Collection engine, API, dashboard, repo, demo. Claude Pro. |
| Bharat | active | Database, loader, index engine, webapp. Claude Pro. |
| Ayush | **left the project** | Was maths/compliance. His work was redistributed. |
| Kritika, Riya, Vidushi | nominal | Assigned PPT + manual fare logging. **Never delivered any of it.** |

Working reality: it is Mayank and Bharat. Assume nobody else contributes unless
told otherwise.

---

## 2. THE PROBLEM STATEMENT

**SIH26056** — Real-time Airfare Price Index for India via automated scraping of
airline and OTA portals, to augment the CPI.
Organisation: **MoSPI**, Data Informatics & Innovation Division.

The brief asks for: an ethical multi-source Python scraper; a cleaned airfare
database; an index-construction module using given routes and weights; a web
dashboard; documentation; automated tests; and 30 days of back-testing against
DGCA monthly average-fare data.

**Two competitors at UPES on the same PS:** AXIOM (SAP 590014747) and HackHers
(590014907). All three were scheduled in the same hour — Group G13, Runway,
originally Monday 7 September 15:00–16:00, four teams sharing 60 minutes.

---

## 3. CURRENT STATUS — UNKNOWN, ASK FIRST

The internal Round 2 presentation was scheduled **Monday 7 September, 15:00**.
As of the end of the previous chat (7 Sep, 23:56) **it was not known whether it
happened, was missed, or moved again.**

**Ask the user what happened before planning anything.** Do not assume.

Deadline history, for context on how much it has moved: idea deadline 20 Sep →
Round 2 on 3–4 Sep → confirmed 4 Sep 15:00 → moved to Monday 7 Sep 15:00.

---

## 4. WHAT APIx IS

A daily, route-level airfare price index for India.

**6 routes × 5 booking windows = 30 observations a day.**
Routes: DEL-BOM, DEL-BLR, BOM-BLR, DEL-CCU, BLR-HYD, MAA-DEL.
Windows: T+1, T+7, T+14, T+21, T+45. (T+21 is deliberate — it matches MoSPI's
own documented domestic collection window.)
Spec held constant: one adult, economy, one-way, cheapest available.

Pipeline: compliance gate → collect → **Bronze** (raw, immutable JSONL) →
**Silver** (parsed, deduped, outlier-flagged) → **Gold** (cell medians → route
index → national APIx) → API + dashboard.

**Framing that matters:** this is a price-measurement instrument that happens to
use the web, not a scraper that computes an index. That distinction is the
entire pitch and the main differentiator against AXIOM.

---

## 5. VERIFIED FACTS — do not re-derive, do not contradict

### 5.1 India DOES publish an airfare index (corrects an earlier team belief)

MoSPI publishes **"Air fare [normal]: economy class [adult]"** — weight **0.08**,
Base 2012=100, All-India Combined, monthly, in the CPI press-release **Annex-V**
key-items table. Recovered from files already on disk by
`scripts/extract_mospi_airfare.py`, which reproduces MoSPI's own published
inflation rates to the decimal (8.29 / 7.79 / 3.16 / 4.38 / 8.24 / 8.56).

| Index, base 2012=100 | May | Jun | Jul | Sep | Oct | Nov |
|---|---|---|---|---|---|---|
| **2024** | 197.9 | 196.3 | 196.1 | 196.5 | 195.4 | 198.5 |
| **2025** | 214.3 | 211.6 | 202.3 | 205.1 | 211.4 | 215.5 |

**The correct pitch line:** *"India measures every airfare in the country with
one number, at weight 0.08, national level only, once a month. It moved 4.4% in
a single month."* The older claim — "India has no airfare index" — is FALSE and
must never be said to a MoSPI judge.

### 5.2 Unverifiable numbers that must not be used

`D:\SIH 2k26\apix-build-plan.html` §01 cites item code 294, COICOP
07.3.3.1.2.01, a state-level spread of 376.09 points, Punjab 432.69, Andhra
Pradesh 56.60, Sikkim exactly 100.00, σ = 7.54%, and −17.8% in March 2025.
**None of those figures appear in any of the 491 downloaded MoSPI CSVs.** Two
files that document calls "already downloaded" do not exist on disk. Treat that
document as untrusted for facts.

### 5.3 Compliance — real, run three times on separate days

Of the 11 named sources: **6 PERMITTED, 5 unreachable (read timeouts).**

- PERMITTED: Air India Express, Akasa Air, SpiceJet, EaseMyTrip, Cleartrip, Ixigo
- Timed out: IndiGo, Air India, MakeMyTrip, Yatra, Goibibo

All six also permit their actual **fare-search paths**, not just `/`. Verdicts
live in `compliance/verdicts/<date>.json`, robots.txt bodies saved verbatim with
SHA-256 in `compliance/evidence/`.

**Honest caveat that must be stated:** a read timeout is NOT proof of a bot wall.
It may be network. Say "could not be checked", never "blocked us".

### 5.4 Real collected data

**Only two days exist: 3 September and 4 September, 30/30 cells each.**
Nothing on 5, 6 or 7 September — three collection days lost. Airfares cannot be
collected retrospectively, so those days are gone permanently.

Sample real measurement — DEL–BOM departing 24 Sep, checked 3 Sep:
cheapest **₹6,090**, median **₹7,675**, dearest **₹24,056** (221 quotes).
A 4× spread in one cell. Cross-checked: Ixigo independently showed the same
₹6,090. The mean of that cell is ~₹8,900 — a price almost nobody paid. That is
the live evidence for using the median.

### 5.5 An actual finding from our own data

Median fares, 3 September, all 30 real cells:

| Route | T+1 | T+7 | T+14 | T+21 | T+45 |
|---|---|---|---|---|---|
| DEL-BOM | 10,086 | 9,914 | 8,374 | 7,675 | 10,121 |
| DEL-BLR | 14,716 | 13,624 | 12,284 | 12,082 | 14,108 |
| BOM-BLR | 16,493 | 13,071 | 8,552 | 8,690 | 8,223 |
| DEL-CCU | 13,667 | 14,614 | 13,876 | 12,304 | 15,523 |
| BLR-HYD | 16,269 | 14,833 | 6,153 | 5,887 | 8,484 |
| MAA-DEL | 14,414 | 13,124 | 13,462 | 12,520 | 15,711 |

**The booking-window curve is U-shaped, not downward-sloping.** T+45 is dearer
than T+21 on four of six routes. BLR–HYD falls 2.8× from T+1 to T+21. No
official index anywhere publishes booking-window curves, so nobody had checked.

**Must be stated as "we observed", never "airfares are"** — two days, six routes.

### 5.6 International benchmarks (verified earlier, live sources)

- **US BLS** — CPI "Airline fares", series `CUUR0000SETG01`, monthly, public API.
- **Eurostat** — HICP `CP0733` "Passenger transport by air", dataset
  `prc_hicp_midx`, monthly.
- Neither is route-level. Neither is daily.

### 5.7 DGCA

12 PDFs on disk (traffic reports + airline operating stats). **They contain no
average-fare data** — only passenger traffic, load factors, cancellations, OTP.
The brief's "back-test against DGCA monthly average fares" rests on a premise
that could not be verified. DGCA deep links do not work; cite "dgca.gov.in" plus
a description, never a fabricated URL.

Consequence: **route weights are not derived.** All six routes carry equal
weight (1/6) and every index value is stamped `weights_provisional = true`.
Do NOT hand-type weights to clear that flag.

---

## 6. NON-NEGOTIABLE STANCES

1. **Compliance.** Collect only from sources whose robots.txt and terms permit
   it. Never bypass CAPTCHAs. Never rotate IPs. Restricted sources are logged as
   a reportable coverage gap. The PS asks for both bot-evasion AND robots.txt
   compliance — those cannot both hold, and the tiered-permission answer is the
   design position, not a limitation.
2. **No NULLs.** Every observation carries a status from a frozen vocabulary of
   seven: `OK · SOLD_OUT · NO_SERVICE · SOURCE_DISALLOWED · FETCH_FAIL ·
   BLOCKED · PARSE_FAIL`, across three classes MARKET / POLICY / SYSTEM. A
   sold-out flight and a broken scraper are different facts.
3. **Bronze is immutable.** Raw payloads written before parsing, never edited.
4. **Median, not mean.** Fare distributions are right-skewed.
5. **Flag outliers, never delete.** They are usually real.
6. **No machine learning, deliberately.** This measures, it does not predict.
   "Where's the AI?" → "There is none, on purpose. A model makes the number
   harder to audit, and a statistical office must defend every figure."
7. **Never fabricate** numbers, URLs, citations. Missing content becomes a
   visible `‹add link›` placeholder.
8. **Label simulated data.** 91 days of replay history exist, every row stamped
   `source_class = SIMULATED`, drawn differently on charts, named out loud
   before anyone asks.

---

## 7. TECH STACK AND WHY

| Layer | Choice | Reason |
|---|---|---|
| Language | Python 3.12 on Windows 11 | one language for collection + stats |
| Browser | Playwright + Chromium | network interception captures the fare API's JSON directly, already split base/tax/total |
| Database | **SQLite** | **Docker, WSL2 and Postgres are NOT installed on the build machine.** Installing them meant two reboots 24h before a demo. `db/schema.postgres.sql` ships as the production target and as the answer to "why SQLite?" |
| API | FastAPI | auto-generates the OpenAPI docs the brief requires |
| Dashboard | static HTML + vendored ECharts | no npm, no build, works offline |
| Tests | pytest | brief requires automated testing |

**Deliberately excluded by the agreed cut line:** Docker, Postgres running, CI,
auth/IAM, forecasting/ML, anti-bot work, a second live source.

**Key architectural decision:** Bronze is **JSONL files on disk**
(`data/bronze/<date>/<source>.jsonl`), not database rows. Reasons: the raw
archive survives the DB being dropped; collection runs before the DB exists so
two people work in parallel; and "where is your raw data?" is answered by
opening a file. The 14-key record format is frozen.

---

## 8. REPO

**github.com/mayankmalik263/apix** (private) · local `D:\SIH 2k26\apix` ·
22 commits.

```
apix/
├─ config/basket.yml              6 routes, 5 windows, weights (null → provisional)
├─ compliance/
│  ├─ registry.yml                the 11 sources
│  ├─ verdicts/<date>.json        daily verdict ledger
│  └─ evidence/                   robots.txt verbatim + SHA-256
├─ db/
│  ├─ schema.sql                  SQLite, 7 tables          [Bharat, DONE]
│  └─ schema.postgres.sql         production target         [Bharat]
├─ apix/
│  ├─ vocab.py                    the 7 statuses — FROZEN
│  ├─ config.py                   basket + registry loading
│  ├─ collect/
│  │  ├─ compliance.py            the gate — raises BEFORE any network call
│  │  ├─ bronze.py                the JSONL raw archive
│  │  ├─ base.py                  SourceAdapter — the extension point
│  │  ├─ runner.py                the 30-cell loop
│  │  ├─ live_cleartrip.py        REAL fares + validated parse_quotes()
│  │  └─ replay.py                simulated history, always SIMULATED
│  ├─ load/loader.py              Bronze → Silver           [Bharat, DONE]
│  ├─ index/engine.py             the index maths           [Bharat, DONE]
│  └─ cli.py                      compliance/collect/seed/bronze/sheets
├─ webapp/                        [Bharat] dashboard, API, console, scheduler
├─ scripts/
│  ├─ extract_mospi_airfare.py    the real government series
│  ├─ make_ground_truth_sheets.py pre-filled manual sheets
│  └─ dump_for_check.py           CSV dump for independent spreadsheet checking
├─ data/bronze/<date>/            the raw archive (gitignored)
├─ METHODOLOGY.md                 formulas + justifications
└─ TEAM/                          plans and briefs
```

### Commands

```bash
python -m apix.cli compliance --check          # fetch robots.txt, write verdicts
python -m apix.cli compliance --report         # the 11-source table
python -m apix.cli collect --today --live      # 30 real cells, ~20 min, rate limited
python -m apix.cli collect --today --live --routes DEL-BOM --windows 21   # one cell, ~30s
python -m apix.cli bronze --stats
python -m apix.load.loader                     # Bronze → Silver
python -m apix.index.engine                    # → Gold
python -m uvicorn webapp.backend.app:app --port 8000
```

---

## 9. THE INDEX MATHS

```
Cell median      P(r,w,t) = median{ total_fare : status=OK, is_outlier=false }
Price relative   R(r,w,t) = P(r,w,t) / P(r,w,0)      base = 3 Sep 2026 = 100
Route index      I(r,t)   = 100 × ( Π_w R(r,w,t) )^(1/W)     GEOMETRIC — Jevons
National index   APIx(t)  = Σ_r ω_r · I(r,t)   Σω=1  ARITHMETIC — Laspeyres-type
Coverage         n_observed / n_expected;  SOLD_OUT counts as observed,
                 NO_SERVICE leaves the denominator
Confidence       A: cov≥0.90 AND ≥2 source classes · B: cov≥0.70 · C: below
Outliers         modified Z on MAD, |z| > 3.5 (Iglewicz & Hoaglin). Flag, keep.
```

**Windows multiply, routes add.** Windows are ratios against their own bases, so
they combine multiplicatively; a plain average would let T+1 (dearest, jumpiest)
dominate. Routes carry expenditure weights, like budget shares, so they add.
Getting this distinction right is the difference between "a student built a
scraper" and "a student built an index" — and a jury will ask.

---

## 10. AUDIT OF THE CURRENT BUILD (done 7 Sep, from a clean DB)

### Works, verified by running it

- `db/schema.sql` — 7 tables, applies clean
- Loader — 27,928 Silver rows from 2,790 Bronze records, **idempotent**
  (identical count on re-run, so the UNIQUE key is correct)
- Index engine — runs; **separates LIVE from SIMULATED into different series**,
  which is better than specified
- APIx: 3 Sep = 100.000, 4 Sep = 102.240, coverage 30/30, grade B
- METHODOLOGY §3, §6, §7 written by Bharat and genuinely well argued
- Webapp — dashboard, login, console, `/docs`, scheduler, analytics all load

### Five open problems, worst first

1. **Data API returns 401.** `/v1/apix/latest`, `/v1/apix/series`,
   `/v1/overview` all require an API key. A judge asking "show me the API" gets
   an auth error. Needs a public read path or a pre-made demo key.
2. **`requirements.txt` is missing four packages** — `slowapi`,
   `itsdangerous`, `apscheduler`, `python-multipart`. A fresh clone cannot start
   the webapp. Fatal on any other laptop.
3. **Engine contradicts METHODOLOGY §3.** The engine keeps outliers in the
   median; the doc says exclude them. Verified: recomputing *with* outliers
   matches the engine to 0.00004. Impact — APIx **102.240** (engine) vs
   **102.669** (spec). On DEL–BOM T+45 the median moves ₹7,489 → ₹8,692.
   *The engine's behaviour is arguably better statistics* (the median is already
   robust; the flag rate is only 3.5%, so these are real tail fares). **Pick
   one and make the doc and code agree** — a MoSPI judge will catch the mismatch.
4. **Two schema files applied manually** — `db/schema.sql` AND
   `webapp/backend/schema_web.sql`. Miss the second and the scheduler plus every
   data endpoint crash with `no such table`.
5. **Scope creep against the cut line** — login, sessions, API keys, revocation,
   rate limiting, access log. ~500 lines. The cut line said auth was WON'T /
   zero marks, and it directly caused problems 1 and 2.

### Also outstanding

- **METHODOLOGY has 4 unwritten justification boxes** (§4 base period, §5 why
  MAD not 3σ, §8 sold-out vs broken scraper, §12 simulation model check). These
  were Ayush's; they now belong to Mayank. §8 is the most quotable idea in the
  project.
- **No manual ground-truth data.** Pre-filled sheets exist in `data/`; nobody
  ever filled one. Without it there is no independent validation of the
  collector — only the system asserting its own correctness.
- **No `make demo` / one-command cold start.**
- **No 90-second backup screen recording.**
- **PPT untouched** — still the Round 1 deck, still contains the false "India
  has no airfare index" claim and the unsourced state-level statistics.

---

## 11. HOW THE USER WANTS TO BE HELPED

- **Be concise.** No preamble, no restating the request.
- **Verify before asserting.** If it can be checked against a live source or a
  file on disk, check it. Say plainly when something could not be verified.
- **Flag a problem once**, then continue under stated assumptions. Do not
  re-litigate settled decisions.
- **Never invent** numbers, URLs, citations or capabilities.
- **Plain language over jargon** — the team explains this to non-technical
  judges and two members needed the concepts explained from scratch.
- **British-ish spelling** (organise, behaviour). Currency in ₹ with Indian
  formatting (₹1,00,000).
- **Give tasks one at a time** when asked. The user has repeatedly asked for
  "just tell me what to do, one step" — obey that literally.
- The user sometimes invokes `/caveman` for terse output.
- Commit often, one commit per working feature, message says *why*. Push to
  `main`. Co-author trailer:
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`
- `PYTHONIOENCODING=utf-8` is needed for Unicode console output on this machine.

---

## 12. FIRST THING TO DO IN THE NEW CHAT

**Ask what happened with the Monday 7 September presentation.** Everything else
depends on the answer:

- If it happened → what did the jury say, did you advance, what is the next
  deadline?
- If it moved → what is the new date?
- If it was missed → what are the options now?

Then, whatever the answer, the highest-value technical work is unchanged:
fix the five audit problems in order, resume daily collection (every day not
collected is permanently lost), and get the four remaining METHODOLOGY
justifications written.
