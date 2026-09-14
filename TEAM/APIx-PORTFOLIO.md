# APIx — Real-time Airfare Price Index for India

**Smart India Hackathon 2026 · Problem Statement SIH26056 · MoSPI**
Team TouchGrass.exe (SIH-UPES-2026-T020), UPES Dehradun · August–September 2026
Role: **Team lead and lead engineer**

Live: <https://apix-fz3l.onrender.com> · API docs: <https://apix-fz3l.onrender.com/docs>
Code: `github.com/mayankmalik263/apix` *(private: make it public, or remove this
line, before a recruiter tries it)*

Every number in this document was checked against the repository, the database
and the live deployment on 14 September 2026.

---

## Contents

1. [Copy-ready: resume](#1-copy-ready-resume)
2. [Copy-ready: LinkedIn](#2-copy-ready-linkedin)
3. [The problem](#3-the-problem)
4. [What we built](#4-what-we-built)
5. [Architecture](#5-architecture)
6. [Each component in detail](#6-each-component-in-detail)
7. [Tech stack, and why](#7-tech-stack-and-why)
8. [Engineering decisions worth talking about](#8-engineering-decisions-worth-talking-about)
9. [Bugs found and fixed](#9-bugs-found-and-fixed)
10. [Testing](#10-testing)
11. [Deployment and daily automation](#11-deployment-and-daily-automation)
12. [Results](#12-results)
13. [Who built what](#13-who-built-what)
14. [Outcome](#14-outcome)
15. [What not to claim](#15-what-not-to-claim)

---

## 1. Copy-ready: resume

**APIx: Real-time Airfare Price Index for India** · Smart India Hackathon 2026 (MoSPI) · Team lead
*Python, Playwright, FastAPI, SQLite, GitHub Actions, Render*

- Led a team of 3 engineers to build a daily, route-level airfare price index
  for India's Ministry of Statistics, as an augmentation to the national CPI's
  single monthly airfare figure.
- Built a compliance-gated collection engine in Python and Playwright that
  captures airline fare API responses through browser network interception
  across 6 routes and 5 booking windows (30 observations a day); collected
  16,503 live fare quotes over 3 days at 100% cell coverage.
- Designed a three-layer data pipeline: an immutable raw JSONL archive, a
  parsed SQLite layer, and an aggregated index layer, with a seven-status
  observation vocabulary that separates market outcomes (sold out) from
  collection failures (timeout, parse error).
- Enforced robots.txt compliance in code: a gate that refuses any source not
  cleared that day before a browser launches, stores each robots.txt with its
  SHA-256, and records refusals as reportable gaps. 6 of 11 registered sources
  cleared.
- Shipped a documented REST API (FastAPI, 15 data endpoints on open and keyed
  tiers) and a dashboard where any published number can be traced back to the
  raw payload it was parsed from.
- Deployed on Render with a GitHub Actions cron that runs the daily
  collection and triggers automatic republishing; rebuilt the whole system
  from raw data in one command.
- Found and fixed silent data-loss bugs in the resume logic and the database
  unique key; wrote 61 automated tests, including an independent
  recomputation of the published index that agrees with the engine to four
  decimal places.

**Short version, if you only have room for three lines:**

- Built a compliance-gated airfare collection pipeline (Python, Playwright) for
  India's Ministry of Statistics: 30 observations a day across 6 routes and 5
  booking windows, 16,503 live fare quotes collected at 100% coverage.
- Designed an immutable raw archive → SQLite → index pipeline with a seven-status
  vocabulary, a 15-endpoint FastAPI API, and click-through lineage from any
  published number to its raw payload.
- Deployed on Render with daily GitHub Actions automation; 61 tests, including an
  independent recomputation of the index.

---

## 2. Copy-ready: LinkedIn

### Projects section

**Title:** APIx: Real-time Airfare Price Index for India
**Associated with:** Smart India Hackathon 2026 / UPES
**Dates:** Aug 2026 – Sep 2026
**Skills:** Python · Playwright · FastAPI · SQLite · Data Engineering · Web Scraping · GitHub Actions · REST APIs

**Description:**

India measures every airfare in the country with one number, published once a
month at national level. For Smart India Hackathon 2026 (MoSPI, SIH26056) I led
the team that built APIx, a daily route-level airfare index designed to sit
beside it.

It prices 6 city pairs at 5 booking windows every day, collected through browser
network interception rather than screen scraping, and only from sources whose
robots.txt permits it. Raw responses are archived untouched, parsed with a status
on every observation, and aggregated into a published index with coverage and a
confidence grade attached. Any number on the dashboard can be traced back to the
exact bytes it came from.

We collected 16,503 live fare quotes and found that the booking curve is
U-shaped: on 5 of 6 routes, booking 45 days ahead cost more than booking 21 days
ahead.

Built with Python, Playwright, FastAPI and SQLite, deployed on Render with daily
collection on GitHub Actions. 61 automated tests.

### A note if you write a post about it

The strongest story here is not "we built a scraper". It is the moment the
scheduled job ran from a GitHub server, the airline site refused it with an HTTP
403, and the system recorded four days of honest refusals instead of trying to
get around the block. That was designed in, and it held in production. See
section 11.

---

## 3. The problem

**Smart India Hackathon 2026, problem statement SIH26056.**
Organisation: Ministry of Statistics and Programme Implementation (MoSPI), Data
Informatics and Innovation Division.

The brief: build a real-time airfare price index for India using automated
collection from airline and online travel agency portals, to augment the
Consumer Price Index. It asked for a multi-source collector, a cleaned fare
database, an index-construction module, a web dashboard, documentation and
automated tests.

**What already exists.** MoSPI publishes an item called "Air fare [normal]:
economy class [adult]" inside the CPI, at weight 0.08. It is one national
number, released once a month. It moved 4.4% in a single month in 2025 (211.6 in
June to 202.3 in July), and there was no way to ask which route moved, which week
it happened, or whether it hit people who book early or late.

The US Bureau of Labor Statistics and Eurostat both publish airfare series. Both
are monthly, and neither is route-level.

**The gap APIx fills:** daily frequency, route-level detail, booking-window
detail, and a published methodology with every figure traceable to its source.

---

## 4. What we built

A price-measurement instrument that happens to use the web, rather than a
scraper that happens to compute an average.

**The basket.** 6 routes at 5 booking windows = 30 observations a day.

- Routes: Delhi–Mumbai, Delhi–Bengaluru, Mumbai–Bengaluru, Delhi–Kolkata,
  Bengaluru–Hyderabad, Chennai–Delhi
- Windows: 1, 7, 14, 21 and 45 days before departure. The 21-day window matches
  MoSPI's own documented domestic collection window.
- Specification held constant: one adult, economy, one-way, cheapest available.

**What it delivers:**

| Deliverable | What it does |
|---|---|
| Compliance gate | Checks and stores every source's robots.txt before collection is allowed |
| Collection engine | Captures fare data for 30 cells a day, rate limited |
| Raw archive | Stores every response untouched, before any parsing |
| Parser and loader | Turns raw responses into typed, deduplicated rows with a status on each |
| Index engine | Aggregates cells into route indices and a national index |
| REST API | 15 data endpoints, open and keyed tiers, auto-generated docs |
| Dashboard | Six views, including click-through lineage from any number to its raw bytes |
| Daily automation | Scheduled collection that republishes the site without anyone awake |
| Methodology document | Every formula with a written justification |
| Test suite | 61 tests |

---

## 5. Architecture

```
  compliance gate  ─►  collect  ─►  BRONZE  ─►  SILVER  ─►  GOLD  ─►  API + dashboard
  robots.txt,          Playwright   raw JSONL   parsed rows  cell medians
  checked daily,       network      untouched,  7 statuses,  route indices
  stored with SHA-256  interception append-only outliers     national index
                                                 flagged
```

**Bronze** is the raw archive: every response written to
`data/bronze/<date>/<source>.jsonl` before anything reads it, never edited.

**Silver** is the parsed layer: one row per fare quote, each carrying one of
seven statuses and an outlier score.

**Gold** is the published layer: a median per cell, an index per route, one
national index per day, each with coverage and a confidence grade.

The rule the whole design follows: **a missing price and a broken collector are
different facts, and the system never records them the same way.**

---

## 6. Each component in detail

### 6.1 Compliance gate

- Fetches `robots.txt` for all 11 registered sources (5 airlines, 6 online
  travel agencies) and checks whether each source's actual fare-search path is
  allowed, not just the homepage.
- Writes a dated verdict ledger (`compliance/verdicts/<date>.json`) and stores
  every robots.txt verbatim with its SHA-256 hash as evidence.
- Collection **raises an exception before any network call** if a source lacks
  a `PERMITTED` verdict dated today. Absence of a check is not permission.
- Honours each source's declared crawl delay, and identifies itself with a user
  agent that names the project and gives a contact address.
- Result on a home connection: **6 of 11 sources permitted.** The other 5 timed
  out, which the system records as "could not be checked", never as "blocked",
  because a timeout is not evidence of a bot wall.

No CAPTCHA solving, no IP rotation, no fingerprint spoofing anywhere in the
codebase.

### 6.2 Collection engine

- Drives headless Chromium through Playwright.
- Fare pages on these sites are JavaScript applications: a plain HTTP request
  returns an empty shell, and the fares arrive later from a separate API call.
  The engine **intercepts that API response through the browser's network
  layer** and captures the structured JSON directly.
- That is why it can report base fare, taxes and total separately, which the
  brief required and which screen scraping cannot do reliably.
- Loops over the 30 cells with per-source rate limiting.
- **Resumable:** a re-run skips cells that already produced a market result and
  retries only the ones that failed.

### 6.3 Adaptive parser

- Built on Scrapling's selector engine, which can relocate an element by its
  structure when the CSS class it used to match has changed. The brief names
  "page-structure changes silently breaking the parser" as a risk.
- Every fallback is recorded, so a recovered parse never passes silently as a
  healthy one.
- **Scrapling also ships stealth fetchers** (TLS fingerprint impersonation and
  a Playwright fork built to defeat bot detection). **They are deliberately not
  installed.** Scrapling is used purely as a parser; that module makes no
  network requests.

### 6.4 Raw archive (Bronze)

- Append-only JSONL, one file per day per source, with a frozen record format.
- Stored as files rather than database rows, for three reasons: the archive
  survives the database being dropped (airfares cannot be collected for a past
  date), collection could be built before the database existed so two engineers
  worked in parallel, and "where is your raw data?" is answered by opening a
  file.
- Because bytes are stored before parsing, a parser bug can be fixed and the
  entire history re-derived without collecting anything again.

### 6.5 The seven-status vocabulary

Every observation carries exactly one status. There is no NULL.

| Status | Class | Meaning | Counts as observed |
|---|---|---|---|
| `OK` | Market | Fare captured and parsed | Yes |
| `SOLD_OUT` | Market | We asked; nothing was for sale | Yes |
| `NO_SERVICE` | Market | No flight operates that pair | Leaves the denominator |
| `SOURCE_DISALLOWED` | Policy | We chose not to collect it | No, a gap we chose |
| `FETCH_FAIL` | System | Timeout or network failure | No, counted against us |
| `BLOCKED` | System | A bot wall, never bypassed | No, counted against us |
| `PARSE_FAIL` | System | Fetched, but the page shape changed | No, counted against us |

The database rejects any other value. This is what lets the system report its
own coverage honestly.

### 6.6 Loader (Silver)

- Parses Bronze into typed rows: carrier, base fare, taxes, fees, total, status.
- Flags outliers inside each cell using a modified Z-score on the median
  absolute deviation, and **keeps them**. A fare four times the typical one is
  usually a real last-minute seat.
- **Idempotent:** a unique index on the logical fare key means re-running the
  loader produces an identical row count. Verified at 33,288 rows on repeated
  runs.

### 6.7 Index engine (Gold)

- Median fare per cell (medians, because fare distributions are heavily
  skewed).
- A geometric mean across booking windows gives each route's index; a weighted
  arithmetic mean across routes gives the national index.
- Coverage (observed ÷ expected) and a confidence grade (A/B/C) published beside
  every value.
- Live and simulated data are kept in **separate series** and never mixed.

### 6.8 REST API

- FastAPI, with OpenAPI documentation generated from the code at `/docs`.
- 15 data endpoints, declared once and mounted twice: open at `/public`, and
  key-protected at `/v1`, so the two tiers cannot drift apart.
- API keys are 256 bits of randomness, shown once, stored only as a SHA-256
  hash, with server-enforced scopes.
- Rate limited. Security headers on every response.
- Endpoints include the latest value, the series at daily/weekly/monthly
  frequency, per-route and per-window series, the booking-window curve, fare
  composition, compliance report, archive statistics, methodology, and a
  **lineage endpoint** that walks any published median back to its raw payload
  hash.

### 6.9 Dashboard

- Plain HTML, CSS and JavaScript. No framework, no build step, no npm.
- Apache ECharts and all fonts vendored into the repository, so it renders
  identically with no internet connection.
- Six views: the index and its comparison with the official series, the
  booking-window curve, the 30-cell basket, data quality and compliance, the
  API, and methodology.
- **Lineage drawer:** click any cell to see the published median, the parsed
  fares behind it with their outlier scores, and the stored raw response with
  its SHA-256.
- Designed for projection: type sized in `rem`, a minimum of 11px, every colour
  token measured above 4.5:1 contrast, 44px touch targets, and support for
  reduced-motion, reduced-transparency and high-contrast preferences.

### 6.10 Official series extraction

- A script that recovers MoSPI's published airfare index from downloaded CPI
  press-release tables and reproduces MoSPI's own published inflation rates to
  the decimal, so the comparison on the dashboard uses the real government
  series rather than an approximation.

### 6.11 Labelled simulated history

- 91 days of generated history from a documented, deterministic model, so the
  dashboard can demonstrate a longer series.
- Its seasonality is interpolated from the real MoSPI index.
- Stamped `SIMULATED` at every layer, drawn dashed on every chart, and never
  used to compute a real value.

---

## 7. Tech stack, and why

| Layer | Choice | Why this over the alternatives |
|---|---|---|
| Language | **Python 3.12** | One language for both browser automation and statistics |
| Browser automation | **Playwright + Chromium** | Network interception captures the fare API's JSON directly. Selenium's interception is far weaker; requests/BeautifulSoup can't run JavaScript |
| Parsing | **Scrapling** (parser only) | Relocates elements after site redesigns. Its stealth fetchers are deliberately not installed |
| HTTP | **httpx** | robots.txt checks don't need a browser |
| Database | **SQLite** | Single file, nothing to install or start, can't fail during a demo. A PostgreSQL schema ships as the production target |
| API | **FastAPI + Uvicorn** | Generates its own OpenAPI docs from the code, so documentation can't go stale |
| Rate limiting / sessions | **slowapi, itsdangerous** | Per-client limits and signed session cookies |
| Scheduling | **APScheduler** | In-process daily job, works on both Windows and Linux |
| Charts | **Apache ECharts** (vendored) | No CDN dependency during a demo |
| Frontend | **Plain HTML/CSS/JS** | Nothing to build, nothing to break |
| Tests | **pytest** | 61 tests |
| CI / automation | **GitHub Actions** | Free runner with 7 GB RAM that doesn't sleep, for daily collection |
| Hosting | **Render** | Runs a long-lived Python process, config lives in the repo, redeploys on every push |
| Version control | **Git / GitHub** | Raw data committed alongside code, so every published number is checkable |

**Why not Vercel:** the dashboard, API and docs are served by one Python
process. Splitting the frontend onto Vercel would have meant an API base URL, a
CORS policy and two deployments to keep in step, for no benefit.

---

## 8. Engineering decisions worth talking about

**Intercept the API, don't scrape the screen.** Reading the site's own fare
response gives structured data with base fare and taxes already separated, and
it doesn't break when the visual layout changes.

**Raw bytes before parsing, always.** The archive is immutable and lives outside
the database. Every parser bug becomes a re-run, never a re-collection.

**No NULLs.** A sold-out flight is information about the market. A timeout is
information about us. Collapsing both into an empty cell makes coverage
uncomputable and makes silent failures look like quiet markets.

**Flag outliers, never delete them.** Removing real high fares would be editing
the market instead of measuring it.

**Compliance is a gate, not a guideline.** It raises before the browser
launches. There is no code path that collects from an uncleared source.

**No machine learning, on purpose.** This is a measurement instrument. A model
would make each published figure harder to audit, and a statistical office has
to defend every number it releases.

**One command from nothing.** `python -m scripts.bootstrap` unpacks the raw
archive, applies both schemas, regenerates the labelled history, and builds
Silver and Gold. It is both the cold start for a fresh clone and the build step
of the deployment.

**Serve and collect in different places.** The public web instance never
collects: it has no browser installed. Collection runs where it has the memory
and uptime to run properly.

---

## 9. Bugs found and fixed

Real issues found by running the system, each fixed with a test.

**Failures were being counted as collected.** When the compliance gate refused
a source, it correctly wrote refusal records. The resume logic then read those
records back as "already collected", so re-running after fixing compliance
skipped every cell. Since fares can't be collected for a past date, that would
have lost the day permanently. Fixed so only market results count as collected;
the re-run recovered all 30 cells.

**Two different failures collapsed into one row.** Every non-OK row has an empty
carrier and fare, so the database's unique key couldn't tell a compliance
refusal from a network failure for the same cell, and silently dropped the
second. Seven real failure records disappeared. Added the status to the key.

**A fresh clone couldn't start.** The requirements file was missing five
packages the code needed. Found them by parsing every Python file's imports
instead of reading the file by eye.

**The documentation contradicted the engine.** The methodology said flagged
outliers were excluded from the median; the engine included them. Kept the
engine's behaviour, corrected the document, and added a test that recomputes the
index from raw rows without importing the engine.

**The server's clock was a day behind.** Render runs on UTC; the observation
slot is defined in IST. For five and a half hours a day the server's "today" was
yesterday, which would have put the daily collection and the compliance verdict
it depends on either side of midnight. Fixed by setting the deployment's
timezone.

**The lineage feature showed the wrong source file.** Clicking a live data cell
could show a simulated payload, or a zero-byte refusal record, as the origin of
a median built from 142 real fares. For a feature whose only job is proving
where numbers come from, that was the most serious bug found. Fixed and pinned
with three tests.

---

## 10. Testing

**61 automated tests (pytest), all passing.**

Worth naming:

- **Parser resilience:** every CSS class on the page is renamed, and the test
  checks fares are still recovered and that the fallback is reported.
- **Independent recomputation:** rebuilds the published index from raw rows
  using only the formulas in the methodology document, without importing the
  index engine. Agrees on every live day to better than 0.0001.
- **Lineage provenance:** a live cell is never explained by simulated bytes, the
  payload shown is one that actually produced fares, and the fare count shown
  matches the engine's.
- **Idempotency and failure handling:** re-running the loader changes nothing;
  failed cells are retried and market results are not.

---

## 11. Deployment and daily automation

**Hosting.** One Render web service, configured by `render.yaml` in the
repository. The build installs a serving-only dependency set and runs the
bootstrap, so the database is rebuilt from the raw archive and baked into the
deployed image. Nothing is lost on restart, and no paid storage is needed.

**Daily collection.** A GitHub Actions workflow runs at 20:00 IST: compliance
check, collection, retry of failed cells, Silver and Gold, then it commits the
day's raw file and compliance verdicts back to the repository. That commit
triggers Render to rebuild and republish.

It runs there rather than on the web server because a free web instance sleeps
after 15 minutes idle (the job would never fire), has 512 MB of memory (too
little for Chromium), and wipes its disk on restart (which would destroy an
archive that can't be re-collected).

**What happened in production, stated plainly.** The workflow has run on its
schedule. From GitHub's datacenter IP, Cleartrip responds to its robots.txt with
an **HTTP 403**. The compliance gate treats that as not cleared and refuses to
collect. So the automated runs on 10, 11, 12 and 13 September each recorded
every cell as a policy refusal, with the reason, and committed that record, and
**no new fares have been collected since 8 September.**

That is the system doing what it was built to do. It did not retry from another
IP, disguise itself, or skip the check. It recorded an honest gap. Collecting
new data requires running from a connection the source accepts, which today
means a local machine.

---

## 12. Results

**Live collection, 3 days (3, 4 and 8 September 2026):**

- **16,503** live fare quotes
- **90 of 90** cells observed (100% coverage every day)
- **7** carriers
- National index: **100.00 → 102.24 → 94.26**, confidence grade B

**A finding from our own data: the booking curve is U-shaped.**

Median across all six routes, 8 September 2026:

| Window | T+1 | T+7 | T+14 | T+21 | T+45 |
|---|---|---|---|---|---|
| Median fare | ₹14,781 | ₹10,108 | ₹10,583 | **₹9,043** | ₹11,595 |

- Booking the day before cost **63.4% more** than the cheapest window.
- The cheapest window was **21 days out**, not the earliest.
- Booking **45 days out cost more than 21 days out on 5 of 6 routes.** On
  Delhi–Kolkata it roughly doubled, from ₹8,922 to ₹18,057.

No official statistical series publishes booking-window curves. This is
observed on three days of data across six routes: a finding, not a law.

**Size of the codebase:** about 6,000 lines of Python, 800 of JavaScript, 600 of
CSS and 775 of SQL, across 51 commits.

---

## 13. Who built what

**My work (Mayank Malik, team lead):**

- Project direction, problem framing, and the technical architecture
- **Compliance layer:** source registry, robots.txt checking, verdict ledger,
  SHA-256 evidence store, and the collection gate
- **Collection engine:** Playwright network interception, the 30-cell runner,
  rate limiting, resumable collection
- **Adaptive parser** and the raw archive format
- **Seven-status vocabulary** and the command-line interface
- **Simulated history model** and the **MoSPI official series extraction**
- **Public API tier and API documentation**
- **Dashboard redesign:** projection-ready typography, accessibility, contrast
  measurement, lineage drawer layout
- **Deployment:** Render configuration, one-command bootstrap, serving-only
  dependencies, timezone fix
- **Daily automation:** the GitHub Actions collection workflow
- **Bug fixes** in section 9, and most of the **test suite**
- The methodology **justifications** after a teammate left the project
- The Round 2 demo

**Bharat Jain:**

- **Database schema** (SQLite and the PostgreSQL production target)
- **Loader** from raw archive to parsed rows, including outlier flagging
- **Index engine** and the methodology formulas it implements
- **Web application backend:** the FastAPI app, operator console, sessions and
  API keys, and the in-process scheduler

**Built together:** the overall pipeline design, the methodology document, and
integrating the collection layer with the data layer.

*Ayush worked on the maths and compliance framing early on and left the
project; that work was redistributed.*

---

## 14. Outcome

Presented at the UPES internal Round 2 of Smart India Hackathon 2026 on
8 September 2026, as the final team of the day. **Not selected for Round 3.**

The system is deployed and publicly reachable, the API is documented and open,
and the full code, raw data and methodology are in the repository.

---

## 15. What not to claim

These would not survive a follow-up question from someone who checks.

- **"Collects live fares every day, automatically."** The collection is
  scheduled and runs every day, but the source refuses the scheduler's IP, so no
  fares have been collected automatically. Say: *"daily collection is automated
  and compliance-gated; from a datacenter IP the source refused access, and the
  system recorded that rather than evading it."*
- **"Months of data."** Three live days. The 91-day history is simulated and
  labelled.
- **"Scrapes 11 airlines and travel sites."** 11 sources are registered and
  checked; live collection runs from one.
- **"Won" or "advanced" at SIH.** Presented at the internal Round 2; not selected
  for Round 3.
- **"AI-powered."** There is no machine learning in APIx, deliberately.
- **"Switching to PostgreSQL is a config change."** The schema is written; the
  application code uses the SQLite driver directly and would need changing.
- **Built without AI tools.** AI coding assistants were used during the build.
  If asked, say so plainly: they were a tool, and the design decisions, the
  compliance position and the debugging were ours.
- **The live site loads instantly.** It runs on a free instance that sleeps
  after 15 minutes idle, and takes about 45 seconds to wake.
