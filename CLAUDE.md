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
- `backend/app/cron/` — standalone scripts deployed as their own Railway cron service
- `docs/` — spec and build prompts (source of truth, read before building)
