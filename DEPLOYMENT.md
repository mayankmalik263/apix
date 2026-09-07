# Putting APIx on the internet

Written 8 September 2026, for the SIH internal round the same afternoon.

---

## The short version

**Deploy one service on Render. Do not split the frontend onto Vercel.**

Everything is already in the repo to do it:

1. Push to GitHub (done).
2. Render → **New +** → **Blueprint** → pick the `apix` repo → **Apply**.
3. Wait about four minutes.
4. Open the URL Render gives you.

That is the whole thing. `render.yaml` in the repo root tells Render what to
build, what to run, and that the instance must never try to collect fares.

**Collection is separately automated** and needs no action from you:
`.github/workflows/collect.yml` runs the thirty-cell collection every day at
20:00 IST, commits the raw file, and the commit redeploys Render. See "Where
the daily collection actually runs" below. Trigger it once by hand first, from
the Actions tab, so you find out today rather than tomorrow whether collecting
from a GitHub runner works.

---

## Why not Vercel for the frontend

You asked about Vercel for the frontend and Render for the backend. It is a
completely normal split, and for this project it is the wrong one. Three
reasons, in the order they will bite you:

**The frontend is not separate.** FastAPI already serves `index.html`,
`app.css`, `app.js` and the vendored fonts from the same process that serves
the data. There is no build step and no bundler. Putting the static files on
Vercel does not remove work from Render; it adds a second place to deploy.

**The dashboard calls relative URLs.** `app.js` fetches `/public/overview`,
`/public/lead-time` and so on. Served from the same origin, that works and
needs no configuration. Move the page to `apix.vercel.app` and every one of
those calls goes to Vercel, finds nothing, and the dashboard renders empty.
Fixing it means introducing an API base URL, then a CORS allow-list on the
backend, then keeping the two in step. That is real work, and every part of it
is a new way for the demo to fail at 15:00.

**Two hosts means two cold starts.** Render's free plan sleeps after fifteen
minutes idle and takes roughly fifty seconds to wake. One sleeping service is
a manageable risk you can pre-warm. Two is worse for no benefit.

If you want it on a Vercel domain anyway, point a Vercel rewrite at the Render
URL rather than hosting the files there. That gets you the domain without
splitting the origin.

---

## What the build actually does

`buildCommand` runs two things.

```
pip install -r requirements-web.txt
python -m scripts.bootstrap
```

`requirements-web.txt` is the serving subset: no Playwright, no Scrapling. The
web application imports neither, and they are the two heaviest packages in the
project. Leaving them out is the difference between a build that takes minutes
and one that takes seconds.

`scripts/bootstrap.py` builds the database from raw:

```
data/seed/*.jsonl.gz  ->  Bronze  ->  Silver  ->  Gold
```

The three real collection days (3, 4 and 8 September) travel in the repo as
13 MB of gzip. They expand to 140 MB of raw JSONL on the server, get parsed
into Silver, and are aggregated into the published index. The 91 days of
labelled generated history are not shipped at all: the replay model is
deterministic, so the server regenerates them from the same seed and gets
byte-identical output.

This means the SQLite file is baked into the build. A restart cannot lose data
that is not already in git, which is why the free plan is enough and no
persistent disk is needed.

---

## Where the daily collection actually runs

**In GitHub Actions, not on the web host.** `.github/workflows/collect.yml`
fires at 14:30 UTC, which is the 20:00 IST slot declared in
`config/basket.yml`, and does the full run: compliance check, collect thirty
cells, retry the ones that failed, Bronze, Silver, Gold. It then commits that
day's raw file and that day's compliance verdicts back to this repository,
which triggers a Render redeploy, which rebuilds the index and republishes.

The loop is closed. Nobody has to be awake.

This is not where the scheduler was meant to live. `webapp/backend/scheduler.py`
runs the identical sequence in-process, and on a host that stays awake with a
persistent disk it is the better answer. Three properties of a free web
instance make it impossible there, and none of them are preferences:

| | |
|---|---|
| Sleeps after 15 minutes idle | The job never fires at 20:00 |
| 512 MB of memory | Chromium will not run reliably |
| Filesystem wiped on restart | Destroys an archive that cannot be collected again |

A GitHub runner has none of those problems, and committing each day's raw file
to version control makes the provenance stronger rather than weaker. A judge
can open the exact bytes a published median was parsed from, and check the
SHA-256 we recorded at the time.

`APIX_SCHEDULER=off` on Render therefore stays. The web instance publishes;
it does not collect. It has no browser installed, no compliance verdict dated
today, and no business opening a connection to an airline's servers.

### Testing it before you rely on it

Actions tab → **collect** → **Run workflow**. It takes about twenty-five
minutes, most of that the rate-limited collection itself. Watch for two things:

- **The compliance report.** Six of eleven sources permitted is the expected
  result. Fewer is worth reading carefully before you trust the run.
- **The OK count in the job summary.** Thirty is a full day.

**The known risk:** the runner collects from a datacenter IP, which Cleartrip
may treat differently from a home connection. If it does, the run records
`BLOCKED` or `FETCH_FAIL`, coverage drops, and the confidence grade falls.
That is the system behaving correctly and reporting honestly. It is not fixed
by rotating IPs, and we do not do that. If it happens, collect from a laptop
instead and push the file by hand:

```bash
python -m apix.cli compliance --check
python -m apix.cli collect --today --live
python -c "import gzip,shutil;d='2026-09-09';shutil.copyfileobj(open(f'data/bronze/{d}/cleartrip.jsonl','rb'),gzip.open(f'data/seed/{d}-cleartrip.jsonl.gz','wb'))"
git add data/seed compliance && git commit -m "collection: 2026-09-09" && git push
```

### What it costs

About 4.5 MB of repository growth per collection day, and roughly 25 minutes
of Actions time, which is free on public repositories and well inside the free
allowance on private ones.

---

## Step by step

### 1. Render

- Sign in at <https://render.com> with GitHub.
- **New +** → **Blueprint**.
- Select `mayankmalik263/apix`. Render reads `render.yaml` and shows one
  service called `apix`.
- **Apply**. First build takes three to five minutes, most of it unpacking and
  parsing the archive.

Watch the build log for the four bootstrap stages. The last block prints:

```
  LIVE       3 published days
  SIMULATED  91 published days
```

If it prints `LIVE 0`, the seed did not unpack; check that `data/seed/` is in
the repo and was not caught by `.gitignore`.

### 2. Check it

Replace `<your-url>` with what Render gives you.

```
https://<your-url>/                        the dashboard
https://<your-url>/v1/health               {"status":"ok", ...}
https://<your-url>/public/apix/latest      today's value, no key needed
https://<your-url>/docs                    the API schema
```

`/v1/health` is the health check path, so Render restarts the service if it
stops answering.

### 3. Before the demo

Free instances sleep after fifteen minutes idle. **Open the URL ten minutes
before you present** and leave the tab open. A cold start in front of the jury
is fifty seconds of white screen.

---

## If Render is refused or breaks

**Railway** takes the same repo with no `render.yaml`. Set the build command to
`pip install -r requirements-web.txt && python -m scripts.bootstrap`, the start
command to `python -m uvicorn webapp.backend.app:app --host 0.0.0.0 --port $PORT`,
and `APIX_SCHEDULER=off`. It does not sleep, which is a real advantage, but the
free credit is limited.

**Fly.io** works too and is the best of the three for a demo because it does not
sleep, but it needs a `Dockerfile` and a `fly.toml` that do not exist yet. Do
not start that at 02:00 the night before.

**Nothing works and it is 14:30.** Run it locally and present from `localhost`.
The dashboard, the API and `/docs` are identical. Say plainly that it runs
locally and the deployment is a hosting detail, which is true. Do not spend the
last half hour fighting a platform.

---

## Custom domain, if there is time

Render gives you `apix-xxxx.onrender.com`. If you want something better, add a
domain in **Settings → Custom Domains** and point a CNAME at it. This is
cosmetic and should be the last thing you do, not the first.

---

## What a judge can be shown

| URL | What it proves |
|---|---|
| `/` | The index, live, with coverage and confidence beside it |
| `/#leadtime` | The booking-window curve nothing official publishes |
| `/#basket` | Thirty cells, click one for its lineage back to the payload hash |
| `/#quality` | The seven statuses, and the sources we could not clear |
| `/docs` | A machine-readable API a statistical office could consume |
| `/public/apix/latest` | The same number, no key, from a plain URL |
