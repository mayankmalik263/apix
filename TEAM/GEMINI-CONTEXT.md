# Context prompt for Antigravity (Gemini 3.8 Flash, high)

Paste everything below the line as the first message. It is written to be
self-contained: it replaces the conversation it came from.

---

You are picking up **APIx**, mid-build, hours before it is judged. Read this
whole file before doing anything. Do not re-derive facts stated here, and do
not contradict them.

## Who and what

**Team TouchGrass.exe**, SIH-UPES-2026-T020, UPES Dehradun.
Lead: **Mayank Malik** (collection, compliance, API, dashboard, repo).
**Bharat** (database, loader, index engine, webapp). Ayush left the project.
Three other members were assigned the PPT and manual fare logging and delivered
neither. Assume two people.

**Problem statement SIH26056** — a real-time airfare price index for India via
automated collection from airline and OTA portals, to augment the CPI.
Organisation: **MoSPI**, Data Informatics & Innovation Division.

**The internal Round 2 presentation is 8 September 2026, 15:00 IST.** They are
the last team of the entire UPES internal hackathon. Two other UPES teams are
on the same problem statement: AXIOM and HackHers.

**Repo:** `github.com/mayankmalik263/apix` (private). Local: `D:\SIH 2k26\apix`.
Windows 11, PowerShell 5.1 (no `&&`; use `;`). Python 3.12. `PYTHONIOENCODING=utf-8`
is needed for Unicode console output on this machine.

## What APIx is

A daily, route-level airfare price index. **6 routes × 5 booking windows = 30
observations a day.** Routes: DEL-BOM, DEL-BLR, BOM-BLR, DEL-CCU, BLR-HYD,
MAA-DEL. Windows: T+1, T+7, T+14, T+21, T+45 (T+21 matches MoSPI's own
documented domestic collection window). Fare spec held constant: one adult,
economy, one-way, cheapest available.

Pipeline: compliance gate → collect → **Bronze** (raw JSONL, immutable) →
**Silver** (parsed, deduped, outliers flagged) → **Gold** (cell medians → route
index → national APIx) → API + dashboard.

**The framing is the pitch:** a price-measurement instrument that happens to use
the web, not a scraper that computes an index.

## The maths

```
Cell median    P(r,w,t) = median{ total_fare : status = OK }   flagged rows KEPT
Price relative R(r,w,t) = P(r,w,t) / P(r,w,base)     base = 3 Sep 2026 = 100
Route index    I(r,t)   = 100 × ( Π_w R(r,w,t) )^(1/W)    GEOMETRIC, Jevons
National       APIx(t)  = Σ_r ω_r · I(r,t),  Σω = 1        ARITHMETIC, Laspeyres
Coverage       observed / expected; SOLD_OUT counts as observed,
                                    NO_SERVICE leaves the denominator
Confidence     A: cov ≥ 0.90 and ≥ 2 source classes · B: cov ≥ 0.70 · C: below
Outliers       modified Z on MAD, |z| > 3.5 (Iglewicz & Hoaglin). Flag, keep.
```

**Windows multiply, routes add.** Windows are ratios against their own bases so
they combine multiplicatively; a plain mean would let T+1 (dearest, jumpiest)
dominate. Routes carry expenditure weights, like budget shares, so they add. A
jury will ask about this distinction.

## Verified facts — do not contradict these

**India DOES publish an airfare index.** MoSPI publishes "Air fare [normal]:
economy class [adult]", weight **0.08**, Base 2012=100, All-India Combined,
monthly, in the CPI press-release Annex-V key-items table. Recovered from files
on disk by `scripts/extract_mospi_airfare.py`, which reproduces MoSPI's own
published inflation rates to the decimal. It fell **4.4% between June and July
2025** (211.6 → 202.3).

The claim "India has no airfare index" is **FALSE** and must never be said to a
MoSPI judge. The correct line: *India measures every airfare in the country with
one number, at weight 0.08, national level only, once a month.*

**Compliance is real and was run on three separate days.** Of 11 registered
sources: **6 PERMITTED** (Air India Express, Akasa Air, SpiceJet, EaseMyTrip,
Cleartrip, Ixigo), **5 unreachable** (IndiGo, Air India, MakeMyTrip, Yatra,
Goibibo — read timeouts). A read timeout is **not** proof of a bot wall. Say
"could not be checked", never "blocked us". robots.txt bodies are stored
verbatim with SHA-256 in `compliance/evidence/`.

**Real collected data: three days only — 3, 4 and 8 September 2026**, 30/30
cells each. 5, 6 and 7 September were never collected and cannot be recovered.

| Date | APIx | Change | Coverage | Grade |
|---|---|---|---|---|
| 3 Sep | 100.000 | base | 30/30 | B |
| 4 Sep | 102.240 | +2.24% | 30/30 | B |
| 8 Sep | 94.263 | −7.80% | 30/30 | B |

**A real finding from their own data:** the booking-window curve is **U-shaped**,
not downward-sloping. The median bottoms out at T+21 (₹9,043) and rises to
₹14,781 at T+1, a 63.4% spread; T+45 is dearer than T+21 on four of six routes.
No official index anywhere publishes booking-window curves. Must always be
stated as "we observed", never "airfares are" — it is three days of data.

**Sample measurement:** DEL–BOM departing 24 September, checked 3 September:
cheapest ₹6,090, median ₹7,675, dearest ₹24,056, 221 quotes. The mean is about
₹8,900, a price almost nobody paid. That is the live argument for the median.

**91 days of replay history exist**, every row stamped `source_class = SIMULATED`,
drawn dashed, named out loud before anyone asks. Nothing real is computed from it.

**DGCA:** 12 PDFs on disk contain no average-fare data, only traffic, load
factors, cancellations and OTP. The brief's "back-test against DGCA monthly
average fares" rests on a premise that could not be verified. **Route weights
are therefore not derived** — all six carry equal weight (1/6) and every index
value is stamped `weights_provisional = true`. Do not hand-type weights to clear
that flag. Never fabricate a DGCA deep link; cite "dgca.gov.in" plus a
description.

**Untrusted document:** `D:\SIH 2k26\apix-build-plan.html` §01 cites item code
294, COICOP 07.3.3.1.2.01, a state spread of 376.09 points, Punjab 432.69,
Sikkim exactly 100.00, σ = 7.54%, and −17.8% in March 2025. **None of those
figures appear in any of the 491 downloaded MoSPI CSVs.** Treat that file as
untrusted for facts.

## Non-negotiable stances

1. **Compliance.** Collect only where robots.txt and terms permit. Never bypass
   CAPTCHAs. Never rotate IPs. Restricted sources are logged as a reportable
   coverage gap. The brief asks for both bot-evasion and robots.txt compliance;
   those cannot both hold, and the tiered-permission answer is the design
   position, not a limitation.
2. **No NULLs.** Every observation carries one of seven statuses —
   `OK · SOLD_OUT · NO_SERVICE · SOURCE_DISALLOWED · FETCH_FAIL · BLOCKED ·
   PARSE_FAIL` — across three classes MARKET / POLICY / SYSTEM. A sold-out
   flight and a broken scraper are different facts.
3. **Bronze is immutable.** Raw payloads written before parsing, never edited.
4. **Median, not mean.** Fare distributions are right-skewed.
5. **Flag outliers, never delete.** They are usually real.
6. **No machine learning, deliberately.** "Where's the AI?" → "There is none, on
   purpose. A model makes the number harder to audit, and a statistical office
   must defend every figure."
7. **Never fabricate** numbers, URLs, citations or capabilities.
8. **Label simulated data** everywhere it appears.

## Stack, and why

Python 3.12 on Windows 11. Playwright + Chromium (network interception captures
the fare API's JSON directly, already split base/tax/total). **SQLite** —
Docker, WSL2 and Postgres are not installed on the build machine, and installing
them meant two reboots 24 hours before a demo; `db/schema.postgres.sql` ships as
the production target and as the answer to "why SQLite?". FastAPI (auto-generates
the OpenAPI docs the brief requires). Static HTML + vendored ECharts, no npm.
pytest.

Deliberately excluded: Docker, Postgres running, CI, forecasting/ML, anti-bot
work, a second live source.

## State of the build as of 8 September, 02:00

**Working, verified by running it:** the full chain from compliance check to
dashboard. 57 tests pass. `python -m scripts.bootstrap` rebuilds everything from
the raw archive in one command. `python -m webapp.run` serves the dashboard, the
open `/public` feed, the keyed `/v1` API, `/docs` and the operator console from
one process.

**Fixed last night (six commits):** two data-loss bugs in the resume logic and
the Silver unique key; a `requirements.txt` that could not start the app on any
other machine; a `/docs` page that advertised only the key-protected tier; a
contradiction between METHODOLOGY §3 and the index engine; the dashboard
redesigned for a projector and its copy rewritten; a one-command cold start and
a Render deployment.

**Known gaps, all deliberate or unresolved:**
- The PPT is untouched. It is still the Round 1 deck and still contains the
  false "India has no airfare index" claim and the unsourced state-level
  statistics. This is the largest remaining risk.
- No manual ground-truth data. Blank sheets exist in `data/`; nobody filled one.
  There is no independent validation of the collector.
- No backup screen recording of the demo.
- Auth (login, sessions, API keys, rate limiting) was built despite being
  explicitly out of scope. It works; leave it alone.

## How to work with Mayank

- **Be concise.** No preamble, no restating the request.
- **Verify before asserting.** If it can be checked against a live source or a
  file on disk, check it. Say plainly when something could not be verified.
- **Flag a problem once**, then continue under stated assumptions.
- **Never invent** numbers, URLs, citations or capabilities. Missing content
  becomes a visible `‹add link›` placeholder.
- **Plain language over jargon.** He explains this to non-technical judges.
- **British-ish spelling** (organise, behaviour). Currency in ₹ with Indian
  digit grouping (₹1,00,000).
- **One task at a time** when he asks for that. He has repeatedly asked for
  "just tell me what to do, one step" — obey it literally.
- Commit often, one commit per working feature, message says *why*. Push to
  `main`.

## Start here

Ask him what happened since 02:00 on 8 September, and what the deadline looks
like now. Then work on whatever he names. If he has no preference, the highest
value work is the PPT, because it is the only remaining deliverable a jury sees
that has not been touched.
