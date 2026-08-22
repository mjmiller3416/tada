# Tada! integration requirements (Hearth Phase 2)

Hearth's **Clean** and **Chores** views are built and verified against a mock.
To wire them to the real Tada! backend, Tada! must expose a small, device-scoped
API. This document is the exact contract Hearth's client
([`src/lib/tada/client.ts`](../src/lib/tada/client.ts)) already calls.

**Why this doc exists:** a survey of the Tada! backend
(`C:\Users\mjmil\Documents\tada\backend`) found that its current API
**cannot** serve this integration as-is. The gaps below are hard blockers — not
adapter work Hearth can paper over — because they concern authentication and
attribution, which only the backend can grant. Until they land, `/clean` and
`/chores` degrade to a calm "not connected" state and local dev runs on
`HEARTH_TASKS_MOCK=1`.

Once the endpoints exist, wiring Hearth is just setting `TADA_API_URL`,
`TADA_DEVICE_TOKEN`, `TADA_MEMBERS`, and `HEARTH_ADULT_ID` on Railway — no Hearth
code change.

---

## The gaps (what Tada! must add)

| # | Gap | Where (Tada! backend) | What's needed |
|---|---|---|---|
| 1 | **No inbound device token.** Auth is a signed session cookie (`tada_session`) from PIN login only — no `Authorization` header / API-key path. | `app/services/auth_service.py`, `app/routers/auth.py` | A static **device token** (env, e.g. `HEARTH_DEVICE_TOKEN`) accepted as `Authorization: Bearer <token>` on a device-scoped router. It authorizes the *device*, not a user. |
| 2 | **`source` is a closed enum** that rejects `"hearth"`. | `app/schemas/tasks.py` (`CompleteRequest.source` Literal); column is `String(20)` | Add `"hearth"` to the allowed `source` values. The DB column already fits it. |
| 3 | **No acting-member override.** `completed_by` is always the cookie user. | `app/services/scheduling.py` (`complete_task`), `app/routers/tasks.py` | Let a device-token request specify **which member** the completion is attributed to (`completed_by = memberId`), instead of deriving it from a session. |
| 4 | **No single next-task-by-room endpoint.** `/api/focus` returns top-N with no room filter; `/api/sessions/build` returns a room-scoped *list*. | `app/routers/sessions.py` | A read that returns the **one** highest-decay task for a scope (optional room) — Hearth shows one task at a time (spec D4). Reuse the existing decay ranking; just return the head, and accept `room`. |
| 5 | **No per-user server filter on done-today.** `/api/done-today` is whole-household. | `app/routers/done_today.py` | Accept a `member` query param (or a device-scoped variant) that filters completions to one member. Hearth *can* filter client-side, but a server filter keeps the payload honest. |
| 6 | **No per-kid chores aggregate.** `/api/chores` is self-only (the logged-in user) and outstanding-only. | `app/routers/chores.py`, `app/services/scheduling.py` (`chores_for_user`) | A device-scoped read returning, for **each kid**, today's **outstanding + completed** chores. Compose the existing `chores_for_user` with today's `CompletionLog` per `completed_by`. |
| 7 | **No member color field** (informational — Hearth owns color). | — | Nothing required upstream. Hearth maps each Tada! member to a color via `TADA_MEMBERS` → `MEMBERS`, so task columns and calendar chips share one color system (spec §7). |

**CORS is not a blocker.** Tada!'s CORS allows a single origin (`FRONTEND_URL`),
but Hearth calls Tada! **server-to-server** from its own route handlers (the
device token never reaches the browser — spec §3.2), so CORS never applies.

**Scope the device token narrowly** (manual setup, spec §5.3): the reads below
plus `complete_task` and its undo — **no** create/delete of task definitions, no
settings, no reward-state changes. The token may complete as any household member
who uses the wall (the kids and Maryann), which is a broader grant than the old
kid-only write and is acceptable only because the wall is a trusted in-home
device.

---

## The contract Hearth calls

All routes are under **`${TADA_API_URL}/api/hearth`**, authenticated with
`Authorization: Bearer <TADA_DEVICE_TOKEN>`. Shapes below are exactly what
[`src/lib/tada/client.ts`](../src/lib/tada/client.ts) sends and expects; the mock
([`src/lib/tada/mock.ts`](../src/lib/tada/mock.ts)) implements the same shapes.

### `GET /rooms`
Rooms a Clean session can be scoped to. Reuse `GET /api/rooms`, projected down.
```jsonc
// 200
{ "rooms": [ { "id": "kitchen", "name": "Kitchen" } ] }
```

### `GET /next?room=<id>&member=<memberId>`
The single highest-decay task for the session; `room` optional (omitted =
whole-house). `member` is the acting adult (for any per-user decay state).
**Return only id/name/room — never the decay score** (spec D4).
```jsonc
// 200 — a task, or null when nothing is due for the scope (the rest state)
{ "task": { "id": "123", "name": "Wipe down the counters", "room": "Kitchen" } }
{ "task": null }
```

### `GET /done-today?member=<memberId>`
That member's completions today, for the done-today celebration.
```jsonc
// 200
{ "completions": [
  { "completionId": "987", "taskName": "Water the plants",
    "room": "Living Room", "completedAt": "2026-08-16T19:40:00-04:00" }
] }
```

### `GET /kids`
Every kid's outstanding + completed chores for today, keyed by Tada! member id.
Hearth pairs these with its configured kids (a kid with no chores still gets a
column), so returning only the kids you have data for is fine.
```jsonc
// 200
{ "kids": [
  { "memberId": "u-lincoln", "chores": [
      { "id": "c1", "name": "Make your bed", "done": true,  "completionId": "555" },
      { "id": "c2", "name": "Feed the dog",  "done": false }
  ] }
] }
```

### `POST /complete`
Complete a task **as** `memberId`, stamped `source: "hearth"`. Reuse
`complete_task`, with `completed_by = memberId` (gap #3) and the new `source`
(gap #2). Returns the completion id so it can be undone.
```jsonc
// request
{ "taskId": "123", "memberId": "u-lincoln", "source": "hearth" }
// 200
{ "completionId": "987" }
```
Hearth validates `memberId` against its own allowlist (`TADA_MEMBERS`) and
rejects anything else `403` *before* calling this — but Tada! should still only
honor members the device token is scoped to.

### `POST /undo`
Reverse a completion within the day (reuse `POST /api/completions/{id}/undo`).
Return `204`. An out-of-window undo should fail (Tada! returns `409` today) —
Hearth treats any non-2xx as "couldn't undo" and reconciles on the next poll.
```jsonc
// request
{ "completionId": "987", "memberId": "u-lincoln" }
// 204 (no body)
```

---

## Once it's live — operator setup

1. Provision a Tada! device token; set `TADA_API_URL` and `TADA_DEVICE_TOKEN` on
   Railway.
2. Set `TADA_MEMBERS` — the acting-member allowlist linking Hearth member keys to
   Tada! user ids and roles — and `HEARTH_ADULT_ID` (Maryann's Tada! id). See
   [`.env.example`](../.env.example).
3. Remove `HEARTH_TASKS_MOCK` from any real environment (it is dev-only and
   already hard-blocked in production builds).
4. Confirm on the wall: Clean surfaces one task and advances on completion;
   done-today fills; a kid's tap checks off their chore; an out-of-allowlist
   completion is rejected. (All of these are already verified against the mock.)