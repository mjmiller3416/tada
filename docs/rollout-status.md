# Tada — Rollout status

> Tracks the live state of feature flags and any stage-gated rollout — things that are
> **true right now** but not visible from reading the code (a default value in
> `settings_service.py` doesn't say whether anyone has actually flipped it in
> production). Update this file whenever a flag changes on the deployed app, not just
> when the code for it ships. Everything here is a Setting row read at runtime, never a
> code-level toggle — see spec §3 (`Setting`) and §8.

---

## Overlay flags

| Flag | Setting key | Default | Status (2026-08-03) |
|---|---|---|---|
| Zones (FlyLady) overlay | `zones_enabled` | `"false"` | **Off.** Not yet enabled for the household. |
| Seasonal campaigns overlay | `campaigns_enabled` | `"false"` | **Off.** |
| Zone scheduling lane (Phase 10/11 composer) | `zone_lane_enabled` | `"false"` | **Off — blocked on the stage gate below.** |
| Vacation mode | `vacation_until` | unset | Off (no active pause). |

## Phase 11 stage gate — NOT yet cleared

Phase 11's composer path only activates when **both** `zone_lane_enabled` and
`zones_enabled` are `"true"` (`settings_service.lanes_active`). Per the Phase 11 build
prompt, flipping `zone_lane_enabled` on is explicitly gated behind a manual review step
that has **not happened yet**:

1. ☐ Mitchell sits down with Maryann and walks her real task set (All tasks, Chromebook)
   — correcting `task_type` on any task the Phase 10 name-based backfill guessed wrong.
2. ☐ Split any of Maryann's own oversized tasks into zone-mission-sized pieces (the
   Phase 10 template splits only affected *new* generation, never her existing rows).
3. ☐ Sanity-check each room's classification.
4. ☐ Flip `zone_lane_enabled` to `"true"` — surfaced in Settings as "Zone missions keep
   to their week" — **and separately turn on `zones_enabled`** if not already on, since
   `lanes_active` requires both.
5. ☐ Verify one partial zone week and one rollover live on her phone before considering
   this done.

Until step 4, the app runs entirely on the pre-Phase-10 global-decay path in
production, regardless of what's in the codebase — this is the intended rollback-safe
default (spec §4, "the rollback boundary FOREVER after").

**Why track this separately from the spec:** `cleaning-app-spec.md` describes what the
flag *does*; it deliberately doesn't say whether anyone has *flipped* it, because that
would make the spec go stale on every rollout step instead of only on behavior changes.
This file is the one place that answers "is it live yet?" without needing to query
Railway/Postgres directly.

## How to check/change this yourself

```
# read current settings for the owner (user_id=1 in this single-household app)
railway run --service backend python -c \
  "from app.database import SessionLocal; from app.services import settings_service as s; \
   db = SessionLocal(); print(s.get_settings(db, 1))"
```

Or flip a flag from the UI once logged in as owner: Settings → Extras. Update the table
above immediately after changing anything in production — this file is only useful if
it stays truthful.
