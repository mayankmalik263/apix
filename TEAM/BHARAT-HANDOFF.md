# Prompt for Bharat's Claude chat

Paste everything below the line into a fresh Claude Code chat opened in the
`apix` repo. Written 8 September 2026, 02:00.

---

I'm Bharat, on Team TouchGrass.exe (SIH-UPES-2026-T020, UPES Dehradun). We're
building **APIx** for problem statement **SIH26056** — a real-time airfare price
index for India, for MoSPI's Data Informatics & Innovation Division. Our
internal Round 2 presentation is **today, 8 September, 15:00**, and we are the
last team of the whole UPES internal hackathon.

I own the database, the loader, the index engine and the webapp. Mayank owns
collection, compliance, the API and the dashboard. Ayush left the project; his
work was redistributed. Three other members were assigned the PPT and manual
fare logging and delivered none of it. Assume it is the two of us.

**First thing: pull. Mayank worked through last night and pushed six commits.**

```bash
git pull origin main
git log --oneline -7
```

## What APIx is

A daily, route-level airfare price index. Six routes (DEL-BOM, DEL-BLR,
BOM-BLR, DEL-CCU, BLR-HYD, MAA-DEL) at five booking windows (T+1, T+7, T+14,
T+21, T+45) = 30 observations a day. Fare spec held constant: one adult,
economy, one-way, cheapest available.

Pipeline: compliance gate → collect → Bronze (raw JSONL, immutable) → Silver
(parsed, deduped, outliers flagged) → Gold (cell medians → route index →
national APIx) → API + dashboard.

The framing that matters: this is a **price-measurement instrument that happens
to use the web**, not a scraper that computes an index.

## What changed last night

Six commits. In order:

**1. `d6818c4` — two data-loss bugs, both mine to know about**

Collection on 8 September hit the compliance gate before the day's robots.txt
check had run. The gate correctly refused all 30 cells and wrote 30
`SOURCE_DISALLOWED` rows into Bronze. Then `bronze.existing_cells()` read those
rows back as "already collected", so re-running after fixing compliance skipped
every cell. Airfares can't be collected retrospectively, so that would have
silently lost the day.

Fixed: `existing_cells()` now resumes only on MARKET-class results. A POLICY
refusal or a SYSTEM failure is a record of what went wrong, not an observation.

Second bug, same root, **in the schema I wrote**: every non-OK row has NULL
carrier, flight_no and total_fare, so `ux_silver_flight_key` couldn't tell a
`SOURCE_DISALLOWED` cell from a `FETCH_FAIL` cell and `INSERT OR IGNORE`
dropped the second one. Seven real FETCH_FAIL rows for 8 September vanished.
`status` is now part of that unique index. Rebuilt from Bronze: 33,288 rows
built, 33,288 in the database, unchanged on re-run.

**2. `ed6a23c` — the repo wouldn't start on any other machine**

`requirements.txt` was missing four packages the code imports (`slowapi`,
`itsdangerous`, `apscheduler`, `scrapling`) plus `python-multipart`, which
FastAPI needs for the `Form()` login route and which no import statement
reveals. Four listed packages were imported nowhere and were removed. Found by
parsing every `.py` for imports rather than by reading the file.

Also: the API looked key-only. The open `/public` tier you built already
existed but is excluded from the schema, so `/docs` advertised only `/v1` and a
judge's first request got a 401. The `/docs` header now names and links the
public routes.

**3. `be94077` — METHODOLOGY vs the engine**

Section 3 said the cell median excludes flagged rows. Your engine includes
them. Both defensible, only one can be true, and a MoSPI judge reading the doc
against the code would have found it. **The engine is right** — section 5 has
always said rows are flagged and never deleted — so the document was corrected.
No published value changed; 4 September has read 102.240 throughout, and under
the old wording it would have read 102.669.

The three unwritten justification boxes are written. There's now a test,
`tests/test_hand_recompute.py`, that recomputes the published index from the
Silver rows using only the formulas in the document, without importing your
engine. All three live days agree to better than 0.0001 index points.

**4, 5. `353d90a`, `94bf973` — the dashboard**

Redesigned for a projector: type moved from 39 hard-coded px sizes to a rem
scale, tap targets 28px → 44px, contrast measured (every token clears 4.5:1),
the drawer now moves on a real spring, and the three accessibility signals are
handled. Headings rewritten in plainer language. Fonts are vendored locally, so
the page looks identical with the wifi off.

**Nothing in the loader, the index engine or the analytics module was touched.**
The DOM contract was verified before and after: every id `app.js` depends on is
still present.

**6. `d63e96a` — one-command cold start, and deployable**

`python -m scripts.bootstrap` brings the whole system up from nothing: unpack
the raw archive, apply both schemas, regenerate the labelled history, load
Silver, build Gold. Idempotent. The three real collection days now travel in
the repo as 13 MB of gzip in `data/seed/`.

`render.yaml` deploys it as one service. See `DEPLOYMENT.md`.

## Where the numbers stand

Three real collection days, 30/30 cells each:

| Date | APIx | Change | Coverage | Grade |
|---|---|---|---|---|
| 3 Sep | 100.000 | base | 30/30 | B |
| 4 Sep | 102.240 | +2.24% | 30/30 | B |
| 8 Sep | 94.263 | −7.80% | 30/30 | B |

5, 6 and 7 September were never collected and are gone permanently.

## What I want you to do

1. `git pull origin main`, then `python -m scripts.bootstrap`, then
   `python -m webapp.run`. Confirm the dashboard, `/docs` and
   `/public/apix/latest` all work on your machine from a clean clone.
2. Read `d6818c4` and tell me whether the `status`-in-unique-index change has
   any consequence for the loader or the engine that we've missed.
3. Read the METHODOLOGY change in `be94077` and confirm you agree the engine's
   behaviour (flagged rows kept in the median) is what we defend to a jury.
4. Run `python -m pytest -q`. It should say 57 passed.

Ask me anything you need about the parts I own. Don't rewrite the collection or
compliance layer — Mayank owns those and they're settled.
