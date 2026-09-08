# Technical prep — Mayank only

Every technology in APIx: what it is, why we picked it, what we rejected.
No maths in this document. If they ask about medians or geometric means, hand
it to Bharat.

Read the **bold line** in each section. That's the answer. The rest is there
for when they push.

---

## 1. Python 3.12

**What it is:** the language the whole system is written in.

**Why:** one language covers both halves of this project. Browser automation
and web scraping have their best tooling in Python, and so does anything
statistical. Using JavaScript for collection and Python for the index would
have meant two runtimes, two dependency sets and a serialisation format
between them, for no benefit.

**If they ask about performance:** we're bounded by politeness, not by speed.
We deliberately wait between requests. A faster language would spend the same
twenty minutes waiting.

---

## 2. Playwright + Chromium — the collector

**What it is:** a browser automation library. It drives a real Chromium
browser: opens pages, waits for content, and lets you watch the network
traffic the page makes.

**Why we needed a real browser:** airline and OTA fare pages are JavaScript
applications. If you fetch the HTML with a plain HTTP request you get an empty
shell — the fares arrive afterwards, from a separate API call the page makes.
There is nothing to parse in the initial response.

**The part worth saying out loud — we don't scrape the screen:**

> We use Playwright's network interception. When the page calls its own fare
> API, we capture that JSON response directly. So we're reading the same
> structured data the website reads, already separated into base fare, taxes
> and total — not scraping numbers out of rendered HTML and hoping the layout
> holds.

That's why we can report base fare separately from taxes, which the problem
statement asks for and which is impossible to do reliably from screen text.

**Why not Selenium:** older API, slower, and its network interception is far
weaker — that capability is the main reason we chose Playwright.

**Why not BeautifulSoup or plain requests:** they can't execute JavaScript.
There would be no fares on the page to find.

---

## 3. Scrapling — the adaptive parser

**What it is:** a Python parsing library. Its useful property is that it can
re-find an element by its shape and position when the CSS class name it used
to match has changed.

**Why:** the problem statement names this risk directly — *"page-structure
changes silently breaking the parser."* A CSS selector written against today's
markup is a time bomb. The site ships a redesign, the selector matches
nothing, and the series quietly fills with failures until somebody notices.

> We store what an element looked like when it worked. If the literal selector
> stops matching, we relocate it by shape instead of failing. And when we do
> fall back, the record says *how* it was recovered, so a fallback never passes
> silently as a healthy parse.

**Have this ready, it's a strong answer:** Scrapling also ships stealth
fetchers — `StealthyFetcher` and `DynamicFetcher` — that pull in TLS
fingerprint impersonation and a Playwright fork built specifically to defeat
bot detection. **We deliberately do not install or use them.** We use Scrapling
purely as a parser; nothing in that module makes a network request. Fetching
stays on plain Playwright with an identifiable user agent.

That is the cleanest possible answer to "are you evading detection?" — we
literally had the evasion tools available in a library we already depend on,
and chose not to install them.

**Tested:** we have tests that rename every CSS class on the page and check we
still recover the fares.

---

## 4. httpx — compliance checks

**What it is:** a modern HTTP client for Python.

**Why:** fetching a `robots.txt` file needs a plain HTTP request, not a
browser. Launching Chromium to download a text file would be absurd. httpx
over `requests` because it supports timeouts and async cleanly and is actively
maintained.

---

## 5. SQLite — the database

**What it is:** a database that is a single file. No server, no port, no
password, nothing to install or start.

**Why, honestly:**

> Postgres is the right production database and we ship the Postgres schema in
> the repo. We demo on SQLite because it cannot fail on stage. There is no
> service to start, no port to conflict, no connection to drop. Twenty-four
> hours before a presentation that has to run repeatedly, that is the entire
> argument.

**Do not overstate the migration.** `db/schema.postgres.sql` is the schema half
of the job and it's real — it documents exactly what changes and why: the raw
payload column becomes JSONB so the archive is queryable, money columns become
`NUMERIC` because floats lose paise, and timestamps become `TIMESTAMPTZ`.

But there is **no ORM in this project**. Eighteen modules use the `sqlite3`
driver directly. Moving to Postgres means changing the driver and connection
handling in each of them. If asked "how hard is the migration?", say:

> The SQL is portable and written. The application code isn't — we use the
> sqlite3 driver directly rather than an ORM, so that's a real piece of work,
> not a config flag.

*(I corrected two comments in the repo this morning that claimed otherwise.
Don't repeat the old claim.)*

**Why not MongoDB / a NoSQL store:** this data is rigidly relational — an
observation belongs to a cell, a cell belongs to a day, every row has a fixed
schema, and we rely on a unique constraint to make re-running the loader safe.
That's exactly what a relational database is for.

---

## 6. Raw files for the archive, not database rows

**What it is:** every raw response is written to a plain text file
(`data/bronze/<date>/<source>.jsonl`) before anything parses it.

**Why this is a deliberate design decision, not laziness — three reasons:**

1. **It survives the database.** During a two-day build the database gets
   dropped and rebuilt repeatedly. Airfares cannot be collected
   retrospectively, so the raw archive has to outlive it. A file does. A table
   doesn't.
2. **Two people could work in parallel.** Collection had to run before the
   database layer existed, so I wasn't blocked on Bharat and he wasn't blocked
   on me.
3. **"Where is your raw data?" is answered by opening a file**, not by
   explaining a schema.

**The payoff:** because we store bytes before parsing, if the parser is ever
wrong we can fix it and re-derive the entire history from data we already
have. Nothing has to be re-collected.

---

## 7. FastAPI — the API

**What it is:** a Python web framework for building APIs.

**Why:** it generates its own OpenAPI documentation from the code. The problem
statement requires API documentation; with FastAPI, `/docs` is always correct
because it's derived from the actual route definitions rather than written by
hand and left to rot.

**Why not Flask:** no automatic schema generation, no built-in request
validation. We'd be writing and maintaining the docs separately.

**Why not Django:** it's a full stack with an ORM, an admin, templates and
migrations. We need a JSON API. Django would be most of a framework unused.

**One design decision worth mentioning:** the endpoints are declared once and
mounted twice — open at `/public`, key-protected at `/v1`. So the two tiers
physically cannot drift apart. A published statistical series is public
information, so reading it never requires a credential; the key exists so bulk
integration can be attributed and revoked.

---

## 8. Plain HTML, CSS and JavaScript — the dashboard

**What it is:** no framework. No React, no build step, no `npm`. There is no
`package.json` in this repo.

**Why:**

> It has to work offline, in a room we don't control, on a machine that might
> have no internet. A static page has nothing to break. No build step means
> there's no version of this where the demo fails because a build failed.

**Why not React:** we'd get a build pipeline, a dependency tree in the hundreds
of packages, and a bundle to keep in sync — to render six pages of charts and
tables. Nothing here needs component state management.

**Charts: Apache ECharts, vendored.** ECharts is a charting library; "vendored"
means we downloaded the file into the repo instead of loading it from a CDN.
Same reason: a CDN is an internet dependency during a demo.

**Fonts are vendored too** — I moved them off Google Fonts last night. If the
room has no internet, Google Fonts fails silently and every piece of type on
the page changes. 121 KB in the repo removes that risk entirely.

---

## 9. pytest — the tests

**What it is:** Python's standard testing framework. 61 tests currently pass.

**Why it matters here:** the brief requires automated testing. Two tests worth
naming if asked:

- **The parser survives a redesign** — we rename every CSS class on the page
  and check we still recover the fares.
- **The published index is recomputed by hand** — a test that rebuilds the
  index from the raw rows using only the formulas in the methodology document,
  *without importing our engine*. Importing the engine would only prove the
  engine equals itself. They agree to four decimal places.

That second one is the strongest testing answer we have.

---

## 10. APScheduler — the daily schedule

**What it is:** a Python scheduling library. It runs a job at a set time.

**Why:** the collection has to happen at a fixed slot every day. Fares move
through the day, so a series collected at 09:00 one day and 21:00 the next
measures the clock as much as the price.

**Why in the application rather than a system cron job:** it's cross-platform
(we develop on Windows, deploy on Linux), and it means running the whole system
is one command instead of a service plus a separate scheduler configuration.

---

## 11. GitHub Actions — where collection actually runs

**What it is:** GitHub's automation service. It runs a job on their machines on
a schedule, for free.

**Why not just run the scheduler on the web server?** Three reasons, and none
of them are preferences:

| Problem with a free web instance | Consequence |
|---|---|
| Sleeps after 15 minutes idle | The 20:00 job never fires |
| 512 MB of memory | Chromium won't run reliably |
| Filesystem wiped on restart | Destroys an archive we can't re-collect |

> So collection runs on a GitHub runner, which has 7 GB of memory and doesn't
> sleep. It commits each day's raw file back to the repository, and that commit
> triggers the site to rebuild and republish.

**The bit that's actually better this way:** every day's raw data lands in
version control. A judge can open the exact bytes a published number was parsed
from and check the hash we recorded at collection time. That's a stronger
provenance claim than a file sitting on a server nobody outside the team can
see.

**Honest caveat if pressed:** tonight's run is the first from a GitHub IP. If
Cleartrip treats a datacenter address differently, the run records `BLOCKED` or
`FETCH_FAIL`, coverage drops, and the grade falls — the system reporting
honestly. We don't fix that by rotating IPs. We'd collect from a laptop instead.

---

## 12. Render — the hosting

**What it is:** a cloud platform that runs web applications. You point it at a
GitHub repository and it builds and hosts it, redeploying automatically on
every push.

**Why Render:**

> It runs a long-lived Python server process, which is what we need. It reads
> its configuration from a file in our repo, so the deployment is version
> controlled rather than clicked together in a dashboard. And it rebuilds
> automatically when the collector pushes a new day.

**Why not Vercel** *(they may ask this specifically — it's the obvious choice)*:

> Vercel is built for frontends and serverless functions. Ours isn't a
> frontend — the same Python process serves the dashboard, the data API and
> the docs together. Splitting the static files onto Vercel would mean the
> dashboard's API calls now go to the wrong host, so we'd have to introduce an
> API base URL and a CORS policy and keep two deployments in step. That's more
> moving parts and two things that can be asleep instead of one, for no gain.

**Why not AWS or Google Cloud:** they'd do it, but you're configuring a
compute instance, networking, storage and deployment yourself. Render is one
file. For a system this size that's the right trade.

**Why not Heroku:** no meaningful free tier any more.

**One design decision:** the database is rebuilt from the raw archive during
the build, so the database file is baked into the deployed image. That means a
restart can't lose anything that isn't already in git — and it's why we don't
need paid persistent storage.

**Collection is switched off on the deployed instance** (`APIX_SCHEDULER=off`).
It has no browser installed and no business reaching an airline's servers. The
public instance publishes; it doesn't collect.

---

## 13. Git and GitHub

Nothing clever, but have the numbers: the repository has the full history of
this build, each commit explaining *why* rather than what. The raw data is
committed alongside the code, which is what makes every published number
checkable by someone outside the team.

---

## The architecture in one breath

If they ask "walk me through the system", say this and stop:

> Compliance gate, then collection, then three data layers, then the API.
>
> Nothing gets collected until that source's robots.txt has been checked and
> stored **today** — the gate raises before a browser is even launched.
> Collection captures the fare API's own JSON through the browser. That raw
> response is written to disk untouched — we call that Bronze. Bronze is parsed
> into rows with a status on every one — that's Silver. Silver is aggregated
> into the published index — that's Gold. FastAPI serves Gold, plus a lineage
> endpoint that walks any published number back to the bytes it came from.
>
> The rule the whole design follows: a missing price and a broken collector are
> different facts, and the system never records them the same way.

---

## Three technical things I should not claim

1. **"Switching to Postgres is one environment variable."** It isn't — there's
   no ORM. The schema is portable; the code isn't yet.
2. **"Scrapling makes us undetectable."** The opposite is the point. We don't
   install its stealth fetchers at all.
3. **"The site is fully automated end to end and proven."** The daily
   collection is automated and scheduled, but tonight is the first run from a
   GitHub runner. Say "scheduled and running from tonight", not "proven".
