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

## What is deliberately switched off

`APIX_SCHEDULER=off`.

A public instance publishes numbers that were collected elsewhere. It has no
browser installed, no compliance verdict dated today, and no business opening
a connection to an airline's servers. If it tried, the compliance gate would
refuse it anyway, and the refusals would be written into Bronze as
`SOURCE_DISALLOWED` rows.

**Collection stays on your laptop.** Run it there, then push the new day's
Bronze file into `data/seed/` and redeploy. One command each evening:

```bash
python -m apix.cli compliance --check
python -m apix.cli collect --today --live
python - -c "import gzip,shutil,sys;d=sys.argv[1];shutil.copyfileobj(open(f'data/bronze/{d}/cleartrip.jsonl','rb'),gzip.open(f'data/seed/{d}-cleartrip.jsonl.gz','wb'))" 2026-09-09
git add data/seed && git commit -m "collection: 2026-09-09" && git push
```

Render redeploys on push, rebuilds the index, and the live site has the new
day. That keeps the published site honest: every number on it came from a raw
file that is in version control.

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
