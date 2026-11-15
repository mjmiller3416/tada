# Tada — Claude Code project context

Read `docs/cleaning-app-spec.md` fully before making any change in this repo — it is
the persistent source of truth for the product philosophy, tech stack, data model,
decay engine, design system, and phase map. Build prompts for each phase live in
`docs/cleaning-app-build-prompts.md` and reference the spec by section.

Build one phase at a time, in order, and don't start feature work from a later phase
early. Follow the coding conventions in spec §8 (complete files, separated concerns,
additive migrations, no scope creep).

## Repo layout

- `frontend/` — Next.js PWA (Railway service: frontend)
- `backend/` — FastAPI + SQLAlchemy + Alembic (Railway service: backend)
- `backend/app/cron/` — the reminder engine: `reminder_worker.py` (always-on loop) around `send_reminders.py` (one pass), deployed as the Railway service named `cron`
- `docs/` — spec and build prompts (source of truth, read before building)

## Working here

- Windows checkout (CRLF): WSL git shows every file modified. Use `git.exe` for status, commits and pushes. Single branch: `main` is production (Railway auto-deploys `backend`, `frontend`, `cron` on push); there is no `staging`, so the general flow squash-merges into `main`.
- Backend tests from WSL need a Linux venv outside the repo (e.g. `uv venv --python 3.12 <dir> && uv pip install -r backend/requirements-dev.txt`), then `python -m pytest` in `backend/` (SQLite in memory; `tests/conftest.py`). Old migrations are Postgres-only, so `alembic upgrade head` on SQLite fails before 0013 — test a new migration by `create_all` of the older tables, `alembic stamp <prev>`, then upgrade.
- Frontend through Windows: `powershell.exe -NoProfile -Command "Set-Location 'D:\Dev\tada\frontend'; npx tsc --noEmit; npm run build"`.
- How it ships and env vars: `docs/deployment.md`. Flags actually flipped in production: `docs/rollout-status.md`.

## ChatGPT connector (MCP server + OAuth 2.1)

- Production MCP URL: `https://frontend-production-bd82b.up.railway.app/api/mcp` (the URL pasted into ChatGPT's "Add custom MCP server", auth OAuth). The browser and ChatGPT reach the backend only through the frontend's proxy: `next.config.ts` forwards `/api/*` and the three `/.well-known/oauth-*` paths. The public origin (issuer, resource) is `FRONTEND_URL`, never the Host header.
- Backend: `routers/oauth.py` (discovery docs, DCR `/api/oauth/register`, consent page `/api/oauth/authorize`, `/api/oauth/token`, `/api/oauth/revoke`, Settings' `/api/oauth/connections`), `services/oauth_service.py` (the logic), `services/oauth_pages.py` (consent/error HTML), `routers/mcp.py` (stateless JSON-RPC: initialize, ping, tools/list, tools/call), `services/mcp_tools.py` (the tool catalog). Tables `oauth_clients`, `oauth_codes`, `oauth_tokens` (migration 0013); every secret stored as SHA-256. Access tokens 1 h, refresh 90 days from last use and rotated on each refresh, codes 10 min single-use (a replayed code revokes its tokens). PKCE S256 required; every authorize redirect carries `iss`.
- Consent page sign-in: the app's own session cookie if present ("Signed in as …", Allow), otherwise the member's Tada PIN on the same page (10 wrong PINs in 15 min blocks it for a while). Tool calls act as whoever approved; a kid's connection gets the kid's permissions.
- Tools: each is a declaration (method, path, schema, annotations) over one real route; `routers/mcp.py` runs it as an in-process HTTP request to that route with a freshly minted session cookie for the member, so the route's own validation, `require_owner` and side effects apply. Never write SQL in a tool. A new user-facing route needs a tool or a reason in `LEFT_OUT` (`tests/test_mcp_tools.py` fails otherwise); `/api/hearth`, `/api/orbit`, `/api/oauth`, `/api/mcp` are excluded. Route lists come from `app.openapi()` because this FastAPI version wraps included routers (`app.routes` holds no `APIRoute`s).
- Kill switch: `MCP_ENABLED=false` on the backend service (503 on `/api/mcp` and `/api/oauth/*`, 404 on discovery). Disconnect every connection: Settings -> Connected apps -> "Disconnect ChatGPT", or `railway run --service backend python -m scripts.revoke_mcp_connections`.
- Hearth's device token (`/api/hearth`) and Orbit's token (`/api/orbit`) are separate and untouched by this.
