# Deploying APIx

The whole system is one process: the API, the dashboard, the operator console
and the scheduler. There is no separate worker, no queue and no build step.

## Render

1. Push this repository to GitHub.
2. On Render: **New → Blueprint**, point it at the repo. `render.yaml` is picked
   up automatically.
3. Wait for the first build. It installs Chromium, so expect five to ten
   minutes.
4. Open a shell on the service and create your account:

   ```
   python -m apix.cli useradd --email you@example.com --name "Your Name"
   ```

5. Sign in at `/admin` and issue an API key.

## Anywhere that runs Docker

```
docker build -t apix .
docker run -p 8000:8000 -v apix-data:/data apix
```

## Two things that matter more than the host

**Persist `/data`.** Bronze is an append-only archive of fares, and a fare
cannot be collected retrospectively. A deploy that resets the volume destroys
days that can never be recovered. `APIX_DB_PATH` and the raw archive both live
there.

**Do not use an instance that sleeps.** The collection slot is fixed at 20:00
IST. A sleeping instance misses it, and the catch-up run only covers a short
nap — it will not recover a night the machine spent asleep.

## Environment

| Variable | Default | Purpose |
|---|---|---|
| `APIX_DB_PATH` | `./apix.db` | Where the database lives |
| `PORT` | `8000` | Set by most hosts automatically |
| `TZ` | system | Set to `Asia/Kolkata` so logs match the collection slot |

The session signing secret is generated on first run into `.apix_secret` and is
never committed. On a host with a persistent disk, keep it under the mount so
operators are not signed out on every deploy.
