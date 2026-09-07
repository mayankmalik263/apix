# APIx web application

The dashboard, the API, the operator console and the daily scheduler. One
process, no build step, no external services.

Everything in this folder is the serving layer. The measurement pipeline it
reads from lives in `apix/` and is untouched by anything here.

---

## Running it on a laptop that has never seen this project

### macOS / Linux

```bash
git clone <repo-url>
cd apix
bash webapp/setup.sh
```

### Windows

```bat
git clone <repo-url>
cd apix
webapp\setup.bat
```

The script checks the Python version, creates a virtual environment, installs
the packages, downloads the Chromium build Playwright drives, and applies both
database schemas. It takes two to five minutes, most of it Chromium.

Then, in the same terminal:

```bash
# macOS / Linux
source .venv/bin/activate
# Windows
.venv\Scripts\activate

python -m apix.cli useradd --generate-password    # once — prints the password
python -m webapp.run
```

Open <http://localhost:8000>.

| | |
|---|---|
| `/` | Dashboard — index, lead time, basket, quality, API, about |
| `/console` | Operator console — API keys, collection runs, access log |
| `/docs` | Generated OpenAPI schema |

### If something goes wrong

| Symptom | Cause |
|---|---|
| `python: command not found` | On Windows, Python was installed without "Add Python to PATH". Reinstall and tick it. |
| `playwright: Executable doesn't exist` | `python -m playwright install chromium` did not finish. Re-run it. |
| Dashboard loads but every panel is empty | No data yet. Run `python -m apix.cli seed --days 91` for the labelled history, or `collect --today --live` for real fares. |
| `/console` bounces to `/login` | The session expired, or no account exists. Run `useradd`. |
| Port already in use | `python -m webapp.run --port 8100` |

Nothing here needs network access after setup except live collection itself.
The dashboard, the API and the console all run offline against whatever is
already in the archive.

---

## What the pages show

**Index** — the published number with its coverage, confidence grade and the
volume of fares behind it, plotted against the official monthly series. Both
are rebased to 100 at their own first observation, so the comparison is of
movement and frequency rather than rupee level. Daily, weekly and monthly are
a toggle; weekly and monthly are means over the period rather than the closing
value, so the figure does not depend on which weekday a month ended on.

**Lead time** — median fare against how far ahead the seat is booked, overall
and per route, with the change between adjacent windows and per day of extra
lead time. This is the output the brief calls a lead-time elasticity curve, and
it is the one thing a monthly national average cannot carry.

**Basket** — all thirty cells as a heatmap and a table, plus the base fare
separated from taxes and fees. **Selecting any cell opens its provenance**: the
published median, every fare row behind it with its outlier score, and the
stored payload with its SHA-256. That path is what makes "auditable" checkable
rather than an adjective.

**Quality** — the fare distribution, the status vocabulary in use, the fares
flagged inside their own cell, and the compliance verdict for all eleven
registered sources with the hash of the robots.txt actually read.

**API** — the two access tiers and every endpoint.

**About** — the problem, the four calculation steps, how APIx compares to what
already exists, and the stated limitations.

---

## Layout

```
webapp/
├─ run.py                  entry point: python -m webapp.run
├─ setup.sh · setup.bat    one-command setup
├─ backend/
│  ├─ app.py               FastAPI: tiers, pages, static assets
│  ├─ analytics.py         frequencies, lead time, composition, lineage
│  ├─ auth.py              scrypt passwords, sessions, API keys
│  ├─ deps.py              the three access tiers
│  ├─ routes_admin.py      operator console endpoints
│  ├─ scheduler.py         the daily collection slot
│  └─ schema_web.sql       accounts, keys, access log, run history
└─ frontend/
   ├─ index.html · app.css · app.js
   ├─ login.html · console.html · console.js
   └─ vendor/echarts.min.js
```

ECharts is vendored rather than loaded from a CDN, so the dashboard works with
the network off.

---

## Access tiers

| Path | Who | Why |
|---|---|---|
| `/public/*` | open, rate limited | A published statistical series is public information. This is what the dashboard reads. |
| `/v1/*` | API key | The documented surface for institutional consumers. The key makes bulk access attributable, rate-limitable and revocable. |
| `/console` | operator session | Anything that changes the system. |

Keys are 256 bits of randomness, shown once at creation and stored only as a
SHA-256 hash — a lost key is rotated, not recovered. Scopes (`read:index`,
`read:lineage`, `read:compliance`) are enforced at the `/v1` boundary.
Passwords use scrypt with a per-user salt; five failures lock the account for
fifteen minutes, and a failed sign-in does not reveal whether the account
exists.

```bash
curl -H "Authorization: Bearer apix_live_..." localhost:8000/v1/apix/latest
curl -H "X-API-Key: apix_live_..."            localhost:8000/v1/lead-time
```

---

## The scheduler

Collection runs daily at the slot declared in `config/basket.yml`, 20:00 IST.

The slot is fixed rather than chosen for speed. Fares move through the day, so
a series collected at 09:00 one day and 21:00 the next measures the clock as
much as the price. What is optimised is everything around the slot: a catch-up
run if the machine was asleep, resumption of only the cells that failed, and
rate limiting that respects each source's declared crawl delay.

Every run is written to `collection_run` before it starts, so a run that
crashes halfway still leaves a row. A day with no row at all means the
scheduler never fired — a different failure from one that fired and found
nothing, and the two must not look alike.

---

## Checks

```bash
python -m pytest tests/         # unit tests
python scripts/dry_run.py       # ten cold starts, counted, into data/dry_run_log.md
```

The dry run deletes a scratch database, applies both schemas, reparses the raw
archive, recomputes the index, boots the API, serves every page, calls every
open endpoint, walks a lineage path back to a real SHA-256, and checks that the
keyed API and the console refuse an anonymous caller.
