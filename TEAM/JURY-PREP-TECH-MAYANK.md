# Technical prep — Mayank

Every technology: what it is, why we picked it, what we said no to.
No maths here. Maths goes to Bharat.

**Bold = say this. The rest is only if they push.**

---

## Python 3.12

**What:** the language everything is written in.

**Why:** one language for both halves. Browser automation and statistics are
both strongest in Python. Splitting them across two languages would mean two
runtimes and a format to pass data between them, for nothing.

**Speed?** We're limited by politeness, not speed. We wait between requests on
purpose. A faster language would wait just as long.

---

## Playwright + Chromium — collecting the fares

**What:** drives a real Chrome browser. Opens pages, waits, and lets us watch
the network calls the page makes.

**Why a real browser:** fare pages are JavaScript apps. Fetch the HTML
normally and you get an empty shell. The fares arrive later, from a separate
API call the page makes.

**Say this:**
> We don't scrape the screen. We intercept the fare API's own JSON response.
> So we read the same structured data the website reads, already split into
> base fare, taxes and total.

That's why we can report taxes separately, which the brief asks for.

**Not Selenium:** older, slower, much weaker network interception — and
interception is the whole reason we chose Playwright.

**Not BeautifulSoup/requests:** they can't run JavaScript. No fares would exist
on the page to read.

---

## Scrapling — the parser that survives redesigns

**What:** a parsing library that can re-find an element by its shape when the
CSS class name changes.

**Why:** the brief names this risk — *"page-structure changes silently breaking
the parser."* A CSS selector written today is a time bomb. Site redesigns, the
selector matches nothing, the data quietly fills with failures.

**We store what an element looked like when it worked.** If the selector stops
matching, we relocate it. And the record says *how* it was found, so a fallback
never looks like a healthy parse.

**Say this if compliance comes up — it's our best answer:**
> Scrapling also ships stealth tools: TLS fingerprint spoofing and a Playwright
> fork built to defeat bot detection. We didn't install them. We use Scrapling
> only as a parser — that module makes no network requests at all.

We had evasion tools sitting in a library we already use, and chose not to.

**Tested:** we rename every CSS class on the page and check we still get the
fares.

---

## httpx — checking robots.txt

**What:** a modern HTTP client.

**Why:** downloading a text file doesn't need a browser. Launching Chromium
for `robots.txt` would be silly.

---

## SQLite — the database

**What:** a database that's just one file. No server, no port, no password,
nothing to install.

**Say this:**
> Postgres is the right production database and we ship the Postgres schema.
> We demo on SQLite because it can't fail on stage — no service to start, no
> port to clash, no connection to drop.

**If they ask how hard Postgres would be — be careful here:**
> The SQL is written and portable. The application code isn't. We use the
> sqlite3 driver directly rather than an ORM, so it's real work, not a config
> flag.

*(Do not say "one environment variable". Two comments in our repo used to claim
that. It was wrong and it's now fixed.)*

**Not MongoDB:** our data is rigidly relational. Fixed schema on every row, and
we rely on a unique constraint to make re-running the loader safe.

---

## Raw files for the archive, not database rows

**What:** every raw response is saved to a plain file before anything parses it.

**Why — three reasons:**
1. **It outlives the database.** We drop and rebuild the DB constantly. Airfares
   can't be collected for a past date, so the raw archive has to survive it.
2. **We could work in parallel.** Collection ran before Bharat's database
   existed. Neither of us blocked the other.
3. **"Where's your raw data?" is answered by opening a file.**

**The payoff:** if the parser was ever wrong, we fix it and rebuild the whole
history from bytes we already have. Nothing gets re-collected.

---

## FastAPI — the API

**What:** a Python framework for building APIs.

**Why:** it writes its own documentation from the code. The brief requires API
docs, and `/docs` is always correct because it comes from the real routes, not
a file someone updates by hand.

**Not Flask:** no auto docs, no built-in validation. We'd maintain them
ourselves.

**Not Django:** it's a full stack with an ORM, admin and templates. We need a
JSON API.

**One design bit:** endpoints are written once and mounted twice — open at
`/public`, key-protected at `/v1`. The two tiers can't drift apart. A published
statistic is public, so reading it needs no key. The key is for bulk users, so
access can be traced and revoked.

---

## Plain HTML, CSS and JavaScript — the dashboard

**What:** no framework, no build step, no npm. There's no `package.json`.

**Say this:**
> It has to work in a room we don't control. A static page has nothing to
> break, and no build step means no version of this where the demo dies
> because a build failed.

**Not React:** hundreds of packages and a build pipeline to render six pages of
charts. Nothing here needs component state.

**Charts:** Apache ECharts, downloaded into the repo instead of loaded from a
CDN. A CDN is an internet dependency during a demo.

**Fonts:** same, moved off Google Fonts last night. No internet means Google
Fonts fails silently and every bit of text on the page changes.

---

## pytest — the tests

**What:** Python's standard test framework. 61 tests pass.

**Two worth naming:**
- **The parser survives a redesign** — we rename every CSS class and check the
  fares still come out.
- **The index is recomputed by hand** — a test rebuilds the published number
  from raw rows using only the formulas in our methodology doc, *without
  importing our engine*. Importing it would only prove the engine equals
  itself. They match to four decimals.

---

## APScheduler — the daily timer

**What:** runs a job at a set time.

**Why:** collection must happen at the same slot daily. Fares move through the
day, so collecting at 09:00 one day and 21:00 the next measures the clock as
much as the price.

**Why not system cron:** works on both Windows and Linux, and running the whole
system stays one command.

---

## GitHub Actions — where collection actually runs

**What:** GitHub runs a job on their machines, on a schedule, free.

**Why not on the web server:**

| Free web instance | Result |
|---|---|
| Sleeps after 15 min idle | The 20:00 job never fires |
| 512 MB memory | Chromium won't run |
| Wipes its disk on restart | Destroys an archive we can't re-collect |

**Say this:**
> Collection runs on a GitHub machine with 7 GB of memory that never sleeps. It
> commits each day's raw file back to the repo, and that commit rebuilds and
> republishes the site.

**Better this way:** every day's raw data lands in version control. Anyone can
open the exact bytes a number came from and check the hash. Stronger than a
file on a server nobody outside the team can see.

**If pressed:** tonight is the first run from a GitHub IP. If Cleartrip treats
a datacenter address differently, it records `BLOCKED` or `FETCH_FAIL` and
coverage drops — the system being honest. We don't fix that by rotating IPs.

---

## Render — the hosting

**What:** a cloud platform. Point it at a GitHub repo, it builds and hosts it,
and redeploys on every push.

**Why:**
> It runs a long-lived Python process, which is what we need. Its config lives
> in a file in our repo, so the deployment is version controlled instead of
> clicked together in a dashboard. And it redeploys itself when the collector
> pushes a new day.

**Why not Vercel** *(they'll probably ask):*
> Vercel is for frontends and serverless functions. Ours isn't a frontend —
> one Python process serves the dashboard, the API and the docs together.
> Splitting the files onto Vercel means the dashboard's API calls go to the
> wrong host, so we'd add an API base URL and a CORS policy and keep two
> deployments in sync. More to break, nothing gained.

**Not AWS/GCP:** you configure compute, networking, storage and deploys
yourself. Render is one file. For this size, that's the right trade.

**Not Heroku:** no real free tier any more.

**One design bit:** the database is rebuilt from the raw archive during the
build, so it's baked into the image. A restart can't lose anything that isn't
in git — which is why we need no paid storage.

**Collection is off on the live site.** It has no browser and no business
calling an airline's servers. The public instance publishes; it doesn't
collect.

---

## The whole system in one breath

If they say "walk me through it", say this and stop:

> Compliance gate, collection, three data layers, then the API.
>
> Nothing is collected until that source's robots.txt has been checked and
> stored **today** — the gate fires before a browser even opens. Collection
> captures the fare API's own JSON. That raw response is saved untouched, and
> we call that Bronze. Bronze is parsed into rows that each carry a status —
> that's Silver. Silver is aggregated into the published index — that's Gold.
> FastAPI serves Gold, plus an endpoint that walks any number back to the bytes
> it came from.
>
> The rule behind all of it: a missing price and a broken collector are
> different facts, and we never record them the same way.

---

## Three things not to claim

1. **"Postgres is one environment variable."** It isn't. No ORM. Schema is
   portable, code isn't yet.
2. **"Scrapling makes us undetectable."** Opposite. We don't install its
   stealth tools.
3. **"Fully automated and proven."** It's scheduled and runs from tonight.
   Tonight is the first run from a GitHub IP.
