# Tada — Deployment

> How Tada actually gets from a commit to running in production. Read this before
> debugging "is it deployed?" or "why didn't my env var take effect?" — the spec
> (`cleaning-app-spec.md`) covers what the app does, not how it ships.

---

## 1. Railway project layout

Everything lives in one Railway project, **`tada`**, single environment
**`production`**. Four services:

| Service | What it runs | Config file |
|---|---|---|
| `backend` | FastAPI app (`uvicorn`) | `backend/railway.json` |
| `frontend` | Next.js PWA | none — Railway auto-detects (Nixpacks + `npm run build`/`npm start`) |
| `cron` | reminder worker — always on, one pass a minute | `backend/railway.cron.json` |
| `Postgres` | Railway-managed Postgres | n/a (Railway template) |

`backend` and `cron` share the same codebase (`backend/`) but deploy as separate
Railway services with different start commands — see below.

## 2. Deploys are automatic on push to `main`

Railway's GitHub integration builds and deploys `backend` and `frontend` on every push
to `main`. There is no manual deploy step and no staging environment — `main` **is**
production. This is why the repo's own conventions (additive migrations, one phase at
a time, tests before merging) carry real weight: a bad commit is live within roughly a
minute of pushing.

Verify what's actually live at any time:

```
railway service status --all      # SUCCESS/FAILED/STOPPED per service
railway logs --service backend -n 50
railway logs --service backend --build -n 50   # build-time logs, to confirm which commit built
```

`cron` is the always-on reminder worker and must show as running — see §4. A
`STOPPED`/`Completed` state there means reminders are not going out.

## 3. Backend: migrations run automatically

`backend/railway.json`:

```
alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Every backend deploy runs pending Alembic migrations before the server starts. There is
**no separate migration step to remember** — an additive migration merged to `main` is
applied automatically on the next deploy. This is also why the spec's coding
conventions (§8) insist migrations be additive: a bad migration blocks the service from
starting at all (`restartPolicyType: ON_FAILURE`, 10 retries), not just from working
correctly.

To check the deployed schema version directly:

```
railway run --service backend alembic current
```

## 4. Reminder worker (the Railway service named `cron`)

`backend/railway.cron.json`:

```json
{
  "deploy": {
    "startCommand": "python -m app.cron.reminder_worker",
    "restartPolicyType": "ALWAYS"
  }
}
```

The service keeps its historical name, but since September 2026 it is an
**always-on worker, not a Railway cron schedule.** `reminder_worker.py` runs one
pass of `send_reminders.run()` (queries `Reminder` rows due now, sends the matching
web pushes) immediately at startup and then at every wall-clock minute, forever;
`restartPolicyType: ALWAYS` means Railway restarts it if it ever exits.
**`railway service status` must show it running at all times** — a cron-style
`STOPPED`/`Completed` state now means reminders are not going out.

Two settings in the Railway dashboard matter and are NOT expressed by the config
file: the service's **Cron Schedule must be empty** and **App Sleeping must be off**.
If a schedule is ever set again, Railway treats the worker as a cron job — it starts
it once, sees it "still running" at the next trigger, and skips every trigger after
that — and stops restarting it.

Why not Railway's cron schedule: it has a 5-minute floor (the spec wants a minute),
and it skips any trigger while it believes the previous execution is still running.
In production (August–September 2026) the schedule fired exactly once per git
deploy and never again, so every nudge and snooze reminder went out in a batch at
the next deploy — which looked, from her phone, like notifications arriving at
random. A loop has no scheduler to fall out with.

Liveness check: `railway logs --service cron -n 20` shows one
`Checked reminders at …: N due` line per minute. To run a single pass by hand
(locally, or as a one-off catch-up) use `python -m app.cron.send_reminders`.

Note: Railway has deprecated config-as-code files (`railway.json`,
`railway.cron.json`) with a hard cutoff of 2026-12-01; the start command and
restart policy above are mirrored in the dashboard so the service survives that.

## 5. Environment variables

Each service needs a different subset. `backend/.env.example` and
`frontend/.env.local.example` are the source of truth for names and comments — set the
same keys on the matching Railway service (Railway dashboard → service → Variables, or
`railway variables --service <name>`).

| Variable | backend | cron | frontend |
|---|:-:|:-:|:-:|
| `DATABASE_URL` | ✓ | ✓ | |
| `SECRET_KEY` | ✓ | ✓ | |
| `SESSION_MAX_AGE_DAYS` | ✓ | | |
| `FRONTEND_URL` (CORS) | ✓ | | |
| `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` / `VAPID_CLAIMS_EMAIL` | ✓ | ✓ | |
| `MEALGENIE_API_URL` / `MEALGENIE_API_KEY` | ✓ | | |
| `GITHUB_TOKEN` / `GITHUB_REPO` | ✓ | | |
| `NEXT_PUBLIC_API_URL` | | | ✓ |
| `NEXT_PUBLIC_VAPID_PUBLIC_KEY` | | | ✓ |

Notes:
- `NEXT_PUBLIC_*` vars are baked in at **build time** on the frontend — changing one on
  Railway requires a redeploy (`railway redeploy --service frontend`), not just a
  restart.
- `VAPID_PUBLIC_KEY` (backend) and `NEXT_PUBLIC_VAPID_PUBLIC_KEY` (frontend) must be the
  **same value**; `VAPID_PRIVATE_KEY` stays backend-only. Generate both with
  `backend/scripts/generate_vapid_keys.py`.
- `MEALGENIE_API_KEY` must equal the `INTEGRATION_API_KEY` env var on the separate
  enchanted-spoon Railway project (the recipe app, formerly named MealGenie — the
  var names keep the old name) — it's the shared secret for the one-way supply push
  (spec §6).
- Leaving `MEALGENIE_API_URL`/`MEALGENIE_API_KEY` empty disables that integration
  without breaking anything else (supplies still track status locally).
- `GITHUB_TOKEN` is a fine-grained PAT with Issues: write scoped to the one repo named
  in `GITHUB_REPO` (e.g. `mjmiller3416/tada`). Leaving either empty
  disables in-app feedback's GitHub issue creation (the Settings section still submits
  successfully; it just logs the report instead of filing an issue).

## 6. One-off / manual scripts

Run against the Railway Postgres via `railway run` (pulls that service's env vars) or a
local `.env` pointed at the same `DATABASE_URL`:

```
# create/update the single owner account (first deploy, or PIN reset)
OWNER_NAME="..." OWNER_EMAIL="..." OWNER_PIN="1234" \
  railway run --service backend python -m scripts.seed_owner

# generate a VAPID keypair
railway run --service backend python -m scripts.generate_vapid_keys
```

`seed_owner.py` is idempotent on `OWNER_EMAIL` — re-running with the same email updates
name/PIN rather than creating a duplicate.

## 7. Rolling back

Migrations are additive-only by convention (spec §8) specifically so this stays simple:

- **Bad app code, schema is fine:** re-deploy the previous commit
  (`railway redeploy --service backend`, or push a revert commit — reverting is
  preferred so `main` stays the source of truth).
- **Feature misbehaving in production but the code is otherwise fine:** prefer flipping
  the relevant Setting flag off (`zones_enabled`, `campaigns_enabled`,
  `zone_lane_enabled` — see `docs/rollout-status.md`) over a redeploy. Every overlay is
  built to cleanly fall back to the core experience.
- **Migration itself is the problem:** do not hand-edit the deployed schema. Write a new
  additive migration that corrects it — this repo has never needed a `downgrade()` run
  in production and the spec's conventions are written to keep it that way.
