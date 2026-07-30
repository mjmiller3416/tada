# Tada — Build Prompts

---

## Phase 0 — Foundation & scaffold

```
Read cleaning-app-spec.md fully before starting. We're building Phase 0 only: the deployed
empty shell that proves every risky integration works before any feature exists.

Repository & deploy setup (do this first):
- Initialize git with a sensible `.gitignore` (Node/Next, Python, virtualenvs, `.env`/secrets, build artifacts) and make an initial commit.
- If I have the GitHub CLI (`gh`), create the remote repo and push; otherwise give me the exact commands to do it. Use a single `main` branch.
- Railway auto-deploys on push to `main`. I'll connect Railway to the repo and set the env vars in the dashboard myself (list them for me at the end).

Build:
1. A Next.js app configured as an installable PWA — web app manifest (name, icons,
   standalone display) and a service worker registered with a push-event handler
   skeleton that calls showNotification().
2. A FastAPI backend with Railway Postgres, SQLAlchemy models, and Alembic
   migrations. Create the User model now with a role field ("owner" | "kid") and a
   PushSubscription model, even though only the owner will exist yet (see SPEC §2, §3).
3. Login auth: a single owner login, using a long-lived session or PIN so the phone
   doesn't re-prompt constantly. NO IP whitelisting. Include a "subscribe to push"
   flow that requests notification permission, creates a PushSubscription, and stores
   it on the backend.
4. Web Push sending on the backend using pywebpush with a generated VAPID keypair.
   Add a temporary "send test push" endpoint/button so we can prove one push arrives
   on the phone.
5. A Railway cron service (runs every minute) that queries a Reminder table for rows
   due now and sends their pushes — for Phase 0 just wire the skeleton and log; the
   Reminder table can be empty.
6. Deploy all of it to Railway and confirm it runs end-to-end.

Follow the coding conventions in cleaning-app-spec.md §8. When done, give me: the file structure,
the env vars I need to set on Railway, and step-by-step instructions to (a) install
the PWA on an Android phone, (b) grant notification permission, and (c) trigger and
receive the test push.

Do NOT build any cleaning features yet — only the foundation above.
```

**Phase 0 is done when:** the app is deployed on Railway, the owner can log in, the PWA installs on the phone, and a manually triggered test push actually arrives on the phone. Then remove/disable the temporary test-push trigger.

---

## Phase 0.5 — Design foundation

```
Read cleaning-app-spec.md, especially section 5 (design system). Build the design foundation BEFORE
any feature UI, so every later phase composes the same components and Tada looks cohesive
throughout. Do NOT build feature screens here.

Build:
1. Design tokens as the single source of truth — CSS variables (or theme config): the
   palette (coral #D85A30 for primary actions, teal #1D9E75 for Done/success, plus the
   cheerful category tints), typography (a friendly rounded sans, two weights), a spacing
   scale, corner radii (cards ~12px, buttons ~14px, pills fully rounded), and
   motion/transition values. Wire these into the PWA theming.
2. A core set of reusable React primitives that consume ONLY those tokens — no hard-coded
   colors: Button (primary/secondary), Card, Chip/Pill, the one-task FocusCard (room tag,
   task name, time estimate, big Done, quiet Skip, small progress signal), the app shell /
   bottom nav, and a celebration component (the Done pop / session-complete confetti).
3. A component preview ("kitchen sink") page rendering every primitive in its states, so I
   can eyeball the look and feel before we build features.

Only build the primitives we already know we need (from the mockup and SPEC section 5) —
don't speculatively build components no feature has asked for yet; later phases grow the
library from these same tokens. Keep primitives general and composable in a components/ui
folder. Match the bright, warm, no-guilt direction in SPEC section 5. Summarize what you
built when done.
```

**Phase 0.5 is done when:** the design tokens exist as the single source of truth, the core React primitives render correctly on the preview page, and the look matches the bright/playful direction — so feature phases can compose them. (You can also restyle the Phase 0 login here.)

---

## Phase 1 — The spine (core app)

```
Read cleaning-app-spec.md. Build Phase 1 on top of the Phase 0 foundation: the complete core app.

Build:
1. The full data model from SPEC §3 needed for core use: Room, Zone (schema only for
   now), Task, CompletionLog, Reminder, Setting.
2. The decay engine exactly as specified in SPEC §4: the dirtiness ratio, color bands,
   the priority ranking with its tie-breaks, and completion resetting last_done_at and
   writing a CompletionLog. Keep this in a separate, documented scheduling service.
3. Onboarding wizard (Chromebook-first, SPEC §6): capture rooms and household context,
   then AUTO-GENERATE a starter task list with sensible default cadences, time
   estimates, and effort per room, which the owner can then edit.
4. Both planning views (SPEC §6): Room view (grouped, with room aggregate dirtiness)
   and Task/global view (flat, sortable, filterable). Cadence tier presets + custom
   intervals when editing a task.
5. The focus session interaction from SPEC §5 — this is the most important piece.
   "I have X minutes" (configurable budget), plus launching a session scoped to a
   chosen room. One task at a time, big Done + quiet Skip, a small progress signal
   only (never the full list), a micro-celebration on Done, and a session-complete
   celebration.
6. Daily focus home screen: the top 1–3 tasks by priority (N configurable), calm, not
   a wall. Energy filter (quick vs deep). Decay-aware snooze that defers the reminder
   WITHOUT resetting last_done_at and uses no guilt language.
7. Reminders: populate the Reminder table from task due-times / a daily nudge time in
   Settings, so the Phase 0 cron now actually sends real reminders.

Apply the design system in SPEC §5 precisely: coral (#D85A30) primary actions, teal
(#1D9E75) for Done, cheerful color-coded chips, rounded friendly shapes, warm
first-name no-guilt copy. Phone = one-thing-at-a-time; Chromebook = full lists/editing.
Follow SPEC §8 conventions and summarize what you built when done.
```

**Phase 1 is done when:** she can set up her home on the Chromebook, get an auto-generated schedule, and on her phone tap "I have 15 minutes" (or pick a room) and be guided through tasks one at a time with real reminders firing.

---

## Phase 2 — People, supplies, maintenance

```
Read cleaning-app-spec.md. Build Phase 2 on top of Phase 1.

Build:
1. Multi-user (SPEC §6): kids get their own logins (role "kid") with basic
   functionality only — see their assigned and claimable chores and check them off.
   On a kid's completion, send a push notification to the owner. Tasks can be assigned
   to a specific member or left open to claim. NO points, rewards, or gamification for
   the kids' chores. (The owner's own login and full functionality already exist.)
2. Supplies (SPEC §6): a Supply inventory with manual status only (in_stock / low /
   out — never auto-decremented). Link tasks to the supplies they use. When a task
   whose linked supply is low/out surfaces in a session, flag it inline. Tada has NO
   shopping list of its own — when a supply is marked low/out, push it into MealGenie's
   existing shopping list via MealGenie's API (base URL + shared API key from env vars).
   One-way push only; dedupe with a last_pushed_at field so a supply isn't sent twice;
   tag pushed items (source "tada", category "household") so they're distinguishable from
   groceries. Build against the endpoint contract in the "MealGenie integration" section
   below.
3. Maintenance (SPEC §6): support category "maintenance" on tasks with long cadences,
   surfaced in their own section/filter so they don't clutter daily cleaning.

Keep the kid experience simple and role-restricted. Follow SPEC §5 (design/voice) and
§8 (conventions). Summarize what you built when done.
```

**Phase 2 is done when:** a kid can log in, check off a chore, and the owner gets a notification; supplies can be marked low/out and get pushed into MealGenie's shopping list; maintenance tasks live in their own section.

---

## MealGenie integration (do this in the MealGenie repo, alongside Tada's Phase 2)

These changes live on the *MealGenie* side so Tada can push supplies into its shopping list. Coordinate with the in-flight shopping-list **sync refactor** — build against the post-refactor shape (that refactor may already add most of this).

```
Add an endpoint so a trusted first-party app (Tada) can add items to the shopping list.

1. Endpoint: POST /shopping-list/items accepting { name, quantity?, source, category? }.
   Follow the existing repository/service pattern — add a service method that upserts the
   item; do not write to the table directly from the route.
2. Auth: protect it with a shared API key checked from a request header (store the expected
   key as an env var). App-to-app auth between two first-party apps — no OAuth needed.
3. Idempotency: dedupe on the receiving end too — upsert by (name, source) or an external
   id so repeated pushes never create duplicate rows.
4. Tagging: store each item's source ("tada") and category ("household") so household
   supplies can be grouped or labeled separately from groceries.
5. List UI: if we want household supplies visually separated in the shopping-list view, add
   the category as a section or a small tag; if mixing them in with groceries is fine, just
   surfacing the source tag is enough.

Set the SAME shared API key as an env var on both Railway services. Summarize what you
built and give me the exact endpoint contract so the Tada side matches it.
```

**MealGenie side is done when:** the endpoint accepts an authenticated item, dedupes it, tags it with source/category, and a test push from Tada lands in MealGenie's shopping list.

**As built (the contract Tada's `services/mealgenie.py` targets):**

```
POST {MEALGENIE_API_URL}/api/shopping/external/items
Header: X-API-Key: <shared secret>          # MealGenie env: INTEGRATION_API_KEY
Body:   { "name": str, "quantity"?: number, "unit"?: str,
          "source": "tada", "category": "household" }
→ 201 (inserted) or 200 (updated existing); upsert keyed on (name, source).
Items land on the MealGenie account set by INTEGRATION_USER_ID.
```

Tada env vars: `MEALGENIE_API_URL` = MealGenie backend origin (no trailing
slash), `MEALGENIE_API_KEY` = the same value as MealGenie's
`INTEGRATION_API_KEY`.

---

## Phase 3 — Overlays

```
Read cleaning-app-spec.md. Build Phase 3 on top of Phase 2. These are opt-in overlays on the core —
they must NOT replace the decay engine.

Build:
1. Guest / "Chaos Cleaning" mode (SPEC §6): a focus session filtered to guest_facing
   tasks. Trigger: "company in [time]." Fill the time budget by impact — a fast,
   high-visibility punch list that skips deep/hidden tasks.
2. Seasonal campaigns (SPEC §6): a Campaign entity grouping tasks with a date window
   and a progress rollup. Activating one surfaces its task set spread over days and
   tracks % complete. Opt-in.
3. FlyLady zone cleaning (SPEC §6): implement the Zone model and the zone→room mapping
   (default to FlyLady's five zones, but fully editable in onboarding). Derive the
   current zone from today's date, and add a "This week's zone" view that surfaces that
   zone's tasks as a focus session. Seed each zone's task list in FlyLady's structure.
   Keep this as an overlay the owner can toggle on/off — the decay model still drives
   everyday upkeep.

Make sure toggling any overlay off cleanly returns to the core experience. Follow
SPEC §5 and §8. Summarize what you built when done.
```

**Phase 3 is done when:** guest mode produces a fast guest-area punch list, a seasonal campaign tracks progress, and (if enabled) the current FlyLady zone surfaces its tasks — all without disrupting the everyday decay-driven flow.
   
```

Phase 4: Packing Lists

> A self-contained module added after Phases 0–3. It complements the main `cleaning-app-spec.md` — reuse that spec's design system (§5) and reminder plumbing, but this feature has its **own model and logic**. Read alongside `packing-starter-templates.md` (the seed data).

---

## Why this is a separate module (read first)

Packing lists are **not** cleaning tasks and must not be built like them:

- They are **one-off and event-driven** (pack for a move or trip once, then archive) — there is **no decay**. Do NOT give packing items a cadence, a dirtiness ratio, or a `last_done_at`. They do not flow through the scheduling engine.
- Packing is the one place a **full, grouped checklist beats one-at-a-time** — you want the whole list visible so nothing is forgotten. Do NOT route packing through the focus-session flow.

What it *does* reuse, so it feels native rather than bolted-on:

- **The design system** (main SPEC §5): the same bright, playful cards, chips, buttons, and warm copy.
- **The reminder/push plumbing** (Phases 0–1): an optional countdown reminder tied to a list's event date.

Keep it in its own tables, routes (`/packing/...`), services, and pages. Built isolated, it cannot destabilize the working cleaning core.

**Scope for v1:** Maryann-only. No kid assignment, no multi-user sharing on packing (the kids' logins don't touch this feature).

---

## Data model

Templates are just template-flagged lists, so one set of tables covers both.

```
PackingList
  id, name
  category: one of "moving" | "travel" | "events" | "work" | "outdoor" |
            "family_kids" | "emergency" | "shipping_storage" | "everyday" | "custom"
  is_template: bool            # true = a seeded starter template to clone from
  event_date: date (nullable)  # move/trip date; drives the optional reminder
  status: "active" | "archived"
  created_at

PackingSection                 # a group within a list ("Clothes", "Documents", ...)
  id, list_id -> PackingList, name, sort_order

PackingItem
  id, section_id -> PackingSection
  name, quantity (nullable, text or int), notes (nullable)
  packed: bool                 # the checkbox
  sort_order
```

Two levels, matching the request: the **list** has a top-level category (one of the 10), and **within** a list, items are grouped into **sections** (a vacation list can have a "Clothes" section with items under it). Sections belong to a list; items belong to a section.

---

## Behavior

**Templates & creation.** Seed the 10 category templates from `packing-starter-templates.md` as `is_template = true` lists. "New list" offers: pick a template → clone its sections + items into a new `active` list (all items `packed = false`) → name it (default to the template name + date) → optionally set an `event_date`. "Custom" clones an empty list with one "Items" section.

**The checklist UI (NOT the focus flow).** A list opens as the full grouped checklist:
- Sections as headers, items with checkboxes beneath.
- A progress bar — overall (14 of 20 packed) and ideally per-section.
- Check/uncheck items; add, rename, reorder, and delete items and sections; add ad-hoc sections and items.
- Warm, no-guilt tone consistent with the rest of Tada; a small celebration when a list hits 100% packed.

**Multiple active lists at once.** She can run a Moving list and a Travel list in parallel (her current situation). A "Lists" / "Packing" index shows active lists with their progress; archived lists are tucked away but restorable.

**Archiving.** When a trip/move is done, archive the list (don't delete) so it can be reused or referenced later. Reusing an archived list = clone it into a fresh active list.

**Optional reminder (reuses existing plumbing).** If a list has an `event_date`, allow a reminder like "Trip in 3 days — 6 items still unpacked," created through the existing Reminder + Web Push system. One-way nudge; nothing new on the notification side beyond a new reminder source.

**Navigation.** Add "Packing" (or "Lists") as its own section in the app shell — parallel to the cleaning surfaces, never mixed into them.

---

## Build prompt (Phase 4)

```
Read cleaning-app-spec.md (especially section 5, the design system) and packing-starter-templates.md.
Build Phase 4: a Packing Lists module. This is a SEPARATE, self-contained feature — it must
NOT touch the decay/scheduling engine or the focus-session flow, and it has its own tables,
routes, services, and pages. v1 is Maryann-only (the kids' logins do not touch this feature).

Build:
1. Data model + an additive migration: PackingList (name, category [the 10 listed in
   packing-starter-templates.md], is_template bool, event_date nullable, status
   active/archived), PackingSection (list_id, name, sort_order), PackingItem (section_id,
   name, quantity nullable, notes nullable, packed bool, sort_order). No cadence, no
   last_done_at, no dirtiness — packing items do not decay.
2. Seed the 10 category templates from packing-starter-templates.md as is_template=true
   lists with their sections and items (packed=false).
3. Backend routes/services under /packing following the existing repository/service pattern:
   list/create/clone-from-template/archive lists; add/rename/reorder/delete sections and
   items; toggle an item packed. "Create from template" clones the template's sections and
   items into a new active list.
4. Frontend: a "Packing" section in the app shell (parallel to cleaning). A lists index
   showing active lists with progress; a "new from template" picker; and a list detail page
   that renders the FULL grouped checklist — sections with checkboxes, overall and per-section
   progress bars, add/edit/reorder for items and sections. This uses the checklist pattern,
   NOT the one-task-at-a-time focus flow — the whole list stays visible on purpose. Reuse the
   existing UI primitives and the bright, warm, no-guilt design. Small celebration at 100%.
5. Optional reminder: if a list has an event_date, let a reminder ("Trip in N days — X items
   unpacked") be created through the existing Reminder + Web Push system (a new reminder
   source only — no new notification plumbing).

Keep everything in its own module so it can't affect the cleaning core. Follow the SPEC
section 8 conventions and summarize what you built when done.
``

**Phase 4 is done when:** Maryann can create a list from a pre-filled template, see it as a full grouped checklist with progress, check items off, run more than one list at once, archive a finished list, and (optionally) get a countdown reminder before an event date — all without any interaction with the cleaning/decay side of the app.

---

## Working notes

- After each phase, do a quick pass on her actual phone before starting the next — the whole design hinges on the phone feel.
- If a feature starts creeping in scope (the way MealGenie did), park it and finish the phase first.
- Keep the reward system encouraging-only. If any copy or mechanic starts to feel like it's nagging or shaming, cut it — that betrays the core design.

---

## Phase 4.5 — Bugs & hardening

> Everything here is a bug she's living with right now. No new features, no migrations, no
> schema changes. Ship this on its own.

```
Read cleaning-app-spec.md (especially §5 and §8). Build Phase 4.5: bug fixes and hardening
only. NO new features, NO migrations, NO schema changes. Several of these are UI-only fixes
to code that already works on the backend — check before building anything new.

Build:

1. HORIZONTAL SCROLL ON THE LISTS PAGES (mobile). The pages scroll sideways on a phone;
   they should be locked to the viewport width. The CSS applies its guards inconsistently —
   apply them uniformly rather than patching one spot. Known gaps:
   - frontend/src/app/packing/packing.module.css: `.eventLine` has no `overflow-wrap: anywhere`,
     though its siblings `.listName` and `.archivedName` both do.
   - frontend/src/app/packing/packing.module.css: `.templateTile` sits in a
     `grid-template-columns: repeat(2, 1fr)` grid with no `min-width: 0`, so a long template
     name cannot shrink below its content width.
   - frontend/src/app/packing/[id]/list-detail.module.css: `.eventLabel` has `flex: 1` but no
     `min-width: 0`, and sits next to `.countdown` which is `white-space: nowrap`.
   Audit both stylesheets for the same two patterns and fix them all, not just these three.
   DO NOT use `overflow-x: hidden` on a wrapper element to hide the symptom — it creates a
   scroll container and will break the sticky section headers planned for Phase 6.

2. DELETE AN ACTIVE LIST. The backend endpoint already exists and works
   (DELETE /api/packing/lists/{list_id} in backend/app/routers/packing.py — hard delete,
   cascades to sections/items/reminders, templates protected). The frontend already has
   `handleDelete` in frontend/src/app/packing/page.tsx. The ONLY problem is that the ✕ button
   renders exclusively on archived cards, so an active list can't be deleted without archiving
   it first. Surface delete on the list DETAIL page (not on the index card — avoid fat-finger
   deletion next to the tap-to-open target). Keep archive as the primary, gentler action and
   make delete visually secondary. Change the confirm text to name the item count, e.g.
   "Delete 'Great Wolf Lodge Family Trip' and its 147 items? This can't be undone." — she
   hand-entered a 147-item list and an accidental delete would be genuinely costly.

3. SKIPPED TASKS GO TO THE BACK OF THE SESSION. Currently, skipping a task and then tapping
   "keep going" re-serves the same task first. This is NOT a queue-ordering bug: Skip
   deliberately doesn't log or touch `last_done_at`, so rebuilding the session returns the
   same unchanged priority ranking, and the skipped task is legitimately still the top one.
   Fix it client-side in frontend/src/app/session/page.tsx: carry the set of skipped task IDs
   forward across a rebuild and move those tasks to the end of the queue. If every remaining
   task has been skipped, end the session gracefully with warm copy rather than looping.
   CRITICAL: Skip must continue to touch nothing in the decay engine — no `last_done_at`
   write, no CompletionLog, no snooze. It is presentation only.

4. NOTIFICATION TOGGLE READS "OFF" AFTER A FORCE-CLOSE. Diagnosed and confirmed: this is a
   pure UI bug. Push delivery, the stored subscription, OS permission, VAPID, and pywebpush
   are all verified healthy — a push sent while the toggle displayed "not enabled" arrived
   correctly. The toggle reads `pushManager.getSubscription()` before the service worker is
   active after a force-close, gets null, and renders "off".
   Fix: `await navigator.serviceWorker.ready` before reading subscription state anywhere in
   the settings toggle's read path. Note that frontend/src/lib/push.ts already does this
   correctly on the SUBSCRIBE path — copy that pattern to the READ path.
   Also add, as belt-and-braces: on app open, if `Notification.permission === "granted"` but
   no subscription exists, silently re-subscribe without making her tap anything.

5. CRON ROBUSTNESS (backend/app/cron/send_reminders.py). Three fixes:
   - `run()` has no try/except around each `_process()` call. One exception on any single
     reminder aborts the entire run before `db.commit()`, so nothing sends for anyone. Wrap
     each `_process()` individually, log the failure with the reminder id, and continue.
   - The cron logs drops ("Reminder N dropped") but logs nothing on a successful send. Add a
     matching success log line with the reminder id and user. This absence turned two
     diagnoses into guesswork.
   - Add `tag: "daily-nudge"` to the daily nudge's showNotification options in
     frontend/public/sw.js so repeated nudges replace each other instead of stacking up.
     DO NOT change the `icon` or `badge` paths in sw.js — that's deliberately out of scope.

6. PIN UNIQUENESS IN backend/scripts/seed_owner.py. Login is PIN-only and matches against
   every user, taking the first hit. backend/app/routers/members.py enforces uniqueness via
   `_check_pin_free`, but the seed script does not — so seeding a second owner with a
   colliding PIN would silently log one person in as the other. Mirror the same check in the
   script and fail with a clear message rather than writing a duplicate.

Follow the SPEC §8 conventions. When done, summarize what you changed, and explicitly list
anything you found already working that needed no change.
```

**Phase 4.5 is done when:** the lists pages don't scroll sideways on her phone, an active list
can be deleted with an item-count confirm, skipped tasks stop jumping back to the front, the
notification toggle reflects reality after a force-close, one bad reminder can't silence the
whole cron run, and the seed script refuses a duplicate PIN.

---

## Phase 4.6 — Composition & control

> Almost all of this is UI work over capability the backend already has. Still no migrations.

```
Read cleaning-app-spec.md (especially §4, §5, §6). Build Phase 4.6: session composition and
household control. NO migrations — new settings go through the existing per-user key/value
settings service (backend/app/services/settings_service.py), not new columns.

IMPORTANT: items 1 and 2 are UI-only. `scheduling.build_session()` already accepts `minutes`,
`room_id`, `zone_id`, and `effort` together, and /session already reads all of them as query
params. Do not change the scheduling service for these.

Build:

1. TIME SELECTION WHEN STARTING FROM A ROOM. Picking a room currently starts a session with
   no time budget. Add the same "how much time do you have" chips to the room entry point, so
   she can scope a room session to 15 minutes. This resolves to
   /session?room={id}&minutes={n} — the existing flow handles it already.

2. OPTIONAL ZONE FILTER ON "HOW MUCH TIME DO YOU HAVE". Add an optional zone selector to the
   time-box flow on the home screen, resolving to /session?zone={id}&minutes={n}. Show this
   control ONLY when the zones overlay is enabled in settings; it must not appear as a dead
   option for a household that never turned zones on.

3. EDITABLE LAST-DONE DATE. Add "when was this last done?" to the task edit form
   (frontend/src/components/TaskForm.tsx) and the corresponding PATCH handling. The decay
   engine already reads `last_done_at` as its only anchor, so this needs NO new scheduling
   concept — it is exposing a field the engine already consumes. Her use case: "we dusted the
   entire Lego collection a week ago during the move, so don't tell me it's overdue."
   Rules:
   - Cannot be set to a future date.
   - Setting it must NOT write a CompletionLog — this is a correction to history, not a
     completion, and it must not inflate the done-today view or streaks in Phase 5.
   - Clearing it back to null (never done) must be possible.
   - Warm, plain-language copy — "Last done" not "Reset decay anchor".

4. VACATION MODE. A household-wide pause. Her explicit decision on the semantics: PAUSE THE
   NUDGES, KEEP THE DECAY RUNNING. She'd rather come home to an honest picture than a fiction.
   - Store as settings keys (e.g. `vacation_until`, empty = off) through settings_service.
   - The cron (backend/app/cron/send_reminders.py) skips dispatching ALL reminder types for a
     user whose vacation window covers the current moment. It should skip, not deactivate —
     reminders resume by themselves afterwards.
   - The home screen shows a calm paused state with the return date and a one-tap "I'm back"
     to end it early. Warm copy, e.g. "Everything's paused until Aug 3. Have a good trip 🌴"
   - CRITICAL: this must NOT touch `dirtiness_ratio`, `rank_tasks`, or anything else in
     backend/app/services/scheduling.py. Decay continues exactly as normal throughout. That
     isolation is why this phase needs no tests.
   - Leave a clear seam for Phase 5, which will freeze streaks across the same window.

5. "ADD AN ADULT" IN SETTINGS. Owner accounts can currently only be created by
   backend/scripts/seed_owner.py. Add a UI in the Settings → Your crew section
   (frontend/src/components/HouseholdSection.tsx) to create a second `role="owner"` account
   with a name and PIN.
   Notes:
   - Shared access already works — no data is scoped per user, and `require_owner` only checks
     the role — so a second owner sees the same tasks, rooms, supplies, and lists. Nothing
     needs to change for that.
   - backend/app/routers/members.py currently guards with `_get_kid`, which 404s on non-kid
     users. Extend it to manage owner accounts too (create, rename, change PIN), reusing the
     existing `_check_pin_free` check.
   - Block deleting the last remaining owner.
   - Make the difference plain in the copy: an adult sees and can change everything; a kid
     sees only their chores.

6. ASSIGNEE FILTER ON /tasks, DEEP-LINKED FROM YOUR CREW. She wants to tap a person and see
   what's assigned to them. frontend/src/app/tasks/page.tsx already filters by room, effort,
   and category entirely client-side, and TaskRow already renders `assignee_name` — so this
   is frontend-only. Add an assignee filter alongside the existing filter chips, and make each
   row in Settings → Your crew link to /tasks filtered to that person.
   Note: task assignment and the exclusion of delegated tasks from her own surfaces are
   ALREADY BUILT and working (`for_user_id=current_user.id` is passed in /focus and
   /sessions/build; tasks assigned to someone else are already filtered out). Do not rebuild
   that. This item is only about giving her a way to look.

Follow SPEC §8 conventions. When done, summarize what you built and list anything you found
already working that needed no change.
```

**Phase 4.6 is done when:** she can pick a room *and* a time, optionally scope a timed session
to a zone, correct a task's last-done date, pause everything while away without decay
freezing, add a second adult from Settings, and tap a person to see their assigned tasks.

---

## Phase 5 — Rewards & Done Today

> This closes the one real gap the code review found. The `User` model has carried
> `current_streak`, `longest_streak`, and `last_active_date` since Phase 0, and nothing has
> ever written to them. Badges have no tables at all. Everything here is additive and
> positive-only, so it cannot destabilize what she uses daily.

```
Read cleaning-app-spec.md, especially §5 (gamification — badges not levels, forgiving
streaks, no guilt) and §4 (the decay engine). Build Phase 5: the reward system and the
"what did I get done today" view.

CONTEXT — why this is missing: SPEC §7 said badges would seed in Phase 1, but the Phase 1
build prompt never listed badges or streak-updating, and no later phase did either. The
schema fields exist and sit at 0 permanently. `scheduling.complete_task()` resets the decay
curve and writes a CompletionLog, then stops. That function is the seam for all of this.

Build:

1. MIGRATION (additive, follows 0006): two new tables.
   - `badges`: id, code (unique slug), name, description, emoji, criteria_key, sort_order
   - `user_badges`: id, user_id -> users, badge_id -> badges, earned_at
     Unique constraint on (user_id, badge_id) — a badge is earned once and never revoked.
   Do not alter any existing table.

2. STREAK TRACKING, wired into the existing `scheduling.complete_task()` seam.
   A "day" means a calendar day in the user's local timezone (from their settings), not UTC.
   On each completion, for the completing user:
   - If `last_active_date` is today: no change (the day is already counted).
   - If `last_active_date` is null: `current_streak = 1`.
   - Otherwise compute the gap in days between `last_active_date` and today, EXCLUDING any
     days that fall inside a vacation window (Phase 4.6). Then:
       - effective gap of 1 day  -> current_streak += 1
       - effective gap of 2 days -> current_streak += 1  (one missed day is forgiven — this
         is the SPEC §5 grace day; the missed day itself earns no credit)
       - effective gap of 3+ days -> current_streak = 1
   - Always set `last_active_date` to today and
     `longest_streak = max(longest_streak, current_streak)`.
   VACATION FREEZE: days inside a vacation window are neutral — not a break to make up, and
   not credit either. Back from eight days away, her streak reads exactly what it did when
   she left. She asked for this explicitly.
   TONE: a broken streak is never announced, never explained, never apologised for. The UI
   shows the current number and nothing else. No "you lost your streak", no "don't break the
   chain", no warnings that a streak is at risk.

3. BADGES: model, service, and seed set. Keep the award logic in its own service, evaluated
   after a completion and again at session complete. It must be idempotent — never award
   twice, never revoke. Seed at least these, all computable from CompletionLog + User:
   - first_task       — first completion ever
   - tasks_10 / tasks_50 / tasks_100 — cumulative completions
   - streak_3 / streak_7 / streak_30 — streak milestones
   - session_first    — first focus session completed start to finish
   - guest_rescue     — first completion with source "guest_mode"
   - zone_first       — first completion with source "zone"
   - campaign_first   — first campaign finished
   - early_bird       — a completion before 8am local time
   Warm, specific, playful names and copy — these are small gifts, not certifications.
   Wire the award check into the session-complete flow the SPEC §5 focus session already
   describes ("session-complete celebration + badge check"): the celebration exists today,
   the check does not.

4. DONE TODAY VIEW. A new screen showing what she has finished today, read entirely from the
   existing CompletionLog (no new tracking needed):
   - Each completion: task name, room chip, time, and who did it when more than one member is
     active in the household.
   - Her current streak, shown warmly.
   - Badges earned, with anything new since last visit highlighted.
   - CRITICAL: accumulation ONLY. Never a denominator, never a percentage, never "5 of 14",
     never a target. A denominator turns a reward into a scoreboard and inverts the entire
     no-guilt design. Show what she did, full stop.
   - Empty state is calm and unbothered, e.g. "Nothing logged yet today — the day's still
     young ✨". It must never read as a reproach.
   - NOTHING COMPARATIVE ANYWHERE. No side-by-side streaks, no who-did-more, no household
     leaderboard. Attribution answers "is this handled", never "who's pulling their weight".

5. HOME SCREEN GAINS EXACTLY ONE NEW ELEMENT: the entry point to the Done Today view. This
   is a hard constraint, not a preference. The calm home screen is the product. Streaks and
   badges live inside the Done Today view, NOT on the home screen.

6. SESSION TIMER. When she starts a timed session ("I have 20 minutes"), optionally run a
   timer that alerts her when the time is up.
   - Route it through the existing Reminder + cron plumbing (a reminder scheduled at
     now + N minutes), NOT a browser/JS timer — a JS timer dies when the screen sleeps, and
     she is cleaning with the phone in her pocket.
   - "Extend" adds more time: reschedule the reminder AND top up the session queue with
     additional tasks that fit the added minutes. Extending must never leave her with time
     and nothing to do.
   - The alert reads as a win, never as a failure to finish: "That's 20 minutes — look at
     what you got done 🎉", not "Time's up". She asked specifically for a congratulations
     message here.
   - The timer must never auto-close or auto-end her session. She decides when she's done.

Everything in this phase is positive-only and additive. If any copy or mechanic starts to
feel like nagging, scolding, or scorekeeping, cut it — that betrays the core design.

Follow SPEC §8 conventions. When done, summarize what you built.
```

**Phase 5 is done when:** completing a task actually moves her streak, a missed day doesn't
break it, a vacation doesn't either, badges are earned and celebrated at session complete, and
she can tap one new thing on the home screen to see everything she got done today — with no
denominator anywhere.

---

## Phase 6 — Lists generalization

> Maryann uses packing lists constantly and wants them for everything checklist-shaped:
> school supplies, Christmas and birthday gift lists, and one-off task lists with no time
> pressure. None of those need recurrence, due dates, or reminders — so this is a
> generalization of what exists, not a new system.

```
Read cleaning-app-spec.md (§5 design system, §6 feature reference) and the Phase 4 packing
section of cleaning-app-build-prompts.md. Build Phase 6: generalize the packing module into
a general-purpose lists module.

SCOPE DISCIPLINE: "anything checklist-shaped" is unbounded. Build exactly what is listed
below. Do NOT add recurrence, due dates, subtasks, tags, search, attachments, or sharing —
none of her use cases need any of it.

HARD BOUNDARY: list items must NEVER surface on the daily focus home screen or in a focus
session. Cleaning tasks recur and decay; list items are done once and gone. The home screen
holding only the top 1–3 decaying tasks IS the "guide, don't list" principle (SPEC §1), and
letting arbitrary to-dos leak in is the one way this revamp could damage the core.

Build:

1. RENAME, via a data-preserving migration. PackingList -> List, PackingSection -> ListSection,
   PackingItem -> ListItem; tables packing_lists -> lists, packing_sections -> list_sections,
   packing_items -> list_items; the reminders FK packing_list_id -> list_id. Use ALTER TABLE
   RENAME so existing rows survive — she has live lists in there, including a 147-item one
   she entered by hand. Update routes (/api/packing -> /api/lists), services, frontend pages
   (/packing -> /lists), and the nav label "Packing" -> "Lists". Keep a redirect from the old
   frontend route so her home-screen shortcut doesn't break.

2. REPLACE THE CATEGORY ENUM WITH A `kind`. The 10-value packing category becomes
   kind: "packing" | "shopping" | "tasks" | "custom". Migrate every existing value to
   "packing" except "custom", which stays "custom" — the seeded templates keep their own
   names ("Moving", "Travel"), so no identity is lost. `kind` drives small presentation
   differences only:
   - packing: sections, quantity secondary
   - shopping: quantity and price prominent
   - tasks: flat single-section feel
   - custom: no opinion

3. HIDE THE SECTION HEADER WHEN A LIST HAS ONLY ONE SECTION. This is what makes a one-off
   task list read as a plain list instead of a form, reusing the structure already there.

4. COLLAPSIBLE SECTIONS. Her Great Wolf Lodge list is large enough that scrolling it became
   tedious.
   - Persist collapse state in localStorage, keyed per list. NOT in the database: this is a
     per-device view preference — collapsed on her phone while packing, expanded on the
     Chromebook while planning — so syncing it across devices would be actively wrong.
   - A collapsed section header still shows its progress count ("Clothes · 8 of 12"), so
     collapsing hides items, never information.
   - Add "Collapse all / Expand all" to the existing `.toolbar` in the list detail page.
   - Auto-collapse a section when it reaches 100%, on the TRANSITION only — never on load,
     so unchecking something doesn't fight her. A big list visibly shrinking as she works is
     the intended feeling.
   - Sticky section headers are a good companion here. If you add them, make sure nothing in
     the ancestor chain sets `overflow-x: hidden` (see Phase 4.5 item 1).

5. PRICES AND RUNNING TOTALS. Add a nullable `price` column, Numeric(10,2), to list items —
   never a float for money. Compute totals in the read model alongside the existing
   packed_count/total_count/percent; do not store them.
   - Show the total ONLY when at least one item on the list has a price, or every packing
     list sprouts a pointless $0.00.
   - Show two figures: the list total and the checked total. On a shopping list, checked
     means bought, so the checked total reads as spend-to-date — "$340 of $500".
   - This is deliberately self-contained. A future budget app will consume these per-item
     prices via a one-way push modeled on the MealGenie integration, but build NOTHING toward
     that here: no budget model, no category link, no external calls.

6. NEW STARTER TEMPLATES, seeded the same way the packing templates are: school supplies,
   Christmas gifts, birthday. Gift lists need no schema beyond what now exists — "Emma — Lego
   set — $40" fits name, notes, and price.

7. AMEND SPEC §6. It currently states flatly that Tada has no shopping list of its own
   (supplies push to MealGenie's). One-off shopping lists contradict that line as written.
   Add the distinction explicitly: MealGenie's list is an ongoing replenishment stream, while
   a Christmas or school-supply list is a finite project that gets finished and archived.
   State plainly that these lists do NOT push to MealGenie, so a future session doesn't
   helpfully invent that integration.

Follow SPEC §8 conventions. When done, summarize what you built, and confirm explicitly that
existing list data survived the rename.
```

**Phase 6 is done when:** "Packing" is "Lists", her existing lists survived intact, she can
make a school-supply or gift list from a template, collapse sections on her phone and have it
stick, and see a running total on the lists where she's entered prices.

---

## Phase 7 — Decay engine test suite

> The decay engine is the architectural spine. It's the one module where a silent regression
> quietly corrupts every priority in the app, and it currently has no tests. It's also pure
> logic with an injectable `now` on every function, so this is cheap. This phase gates Phase 8.

```
Read cleaning-app-spec.md §4 (the decay engine) carefully — it is the specification these
tests encode. Build Phase 7: a unit test suite for backend/app/services/scheduling.py.

CRITICAL INSTRUCTION: these tests document CURRENT behavior against SPEC §4. If a test
reveals a genuine discrepancy between the code and the spec, STOP and report it in your
summary. Do NOT silently "fix" the engine — it is running in production for a real user, and
a review in July 2026 found it matches SPEC §4 exactly. A failing test is far more likely to
be a wrong test than a wrong engine.

Set up pytest with whatever fixtures are needed. The pure functions need no database — build
plain Task objects and pass an explicit `now`. For the query-backed functions, an in-memory
SQLite session is fine if the models are compatible; otherwise use a transactional fixture.

Cover:

1. `dirtiness_ratio`: at zero elapsed time, at exactly one cadence, at fractional cadences,
   well past cadence, and for a never-done task (`last_done_at` is null). Include a
   1-day-cadence task and a 365-day-cadence task, since those are the extremes she actually has.

2. Band boundaries: fresh / aging / due / overdue, tested exactly ON each threshold and just
   either side of it. Off-by-one at a band edge is the most likely silent regression, and the
   band drives every color and every copy string in the UI.

3. `rank_tasks`: ordering by priority, every tie-break in SPEC §4 applied in the right order,
   and stability when two tasks are genuinely identical. Include the daily-cadence boost.

4. Never-done handling: a task with `last_done_at = null` sorts where the spec says it should,
   and does not blow up any calculation.

5. `room_aggregate_ratio`: the max/average blend from SPEC §4 — one filthy task colors a room
   without a single red drowning nine greens. Test the empty-room case (returns None).

6. `is_snoozed`: before, exactly at, and after the snooze expiry; and confirm a snooze does
   NOT alter `last_done_at` or the underlying ratio — the task keeps aging quietly.

7. `candidate_tasks` filters, each independently and in combination: the BAND_AGING freshness
   gate, `room_id`, `zone_id`, `effort`, `guest_only` (guest-facing AND quick only), and
   `for_user_id` (tasks assigned to a DIFFERENT member are excluded; her own and unassigned
   tasks still surface).

8. `build_session`: the greedy time-budget fill takes highest priority first and never
   exceeds the budget; the MAX_SESSION_TASKS cap holds; and the no-budget room case returns
   priority order.

9. `complete_task`: resets the decay curve, clears any snooze, and writes a CompletionLog.
   (After Phase 5, also that it updates the streak — extend these tests then.)

No production code changes in this phase unless you find and report a real spec violation
first. Follow SPEC §8 conventions. When done, summarize coverage and flag anything surprising.
```

**Phase 7 is done when:** the engine has real unit tests, they pass, and any discrepancy
against SPEC §4 has been reported rather than quietly patched.

---

## Phase 8 — Preferred-day boost

> Her example: laundry is a Saturday thing, done all at once. This is the one request that
> genuinely tests the architecture, because Tada is deliberately decay-driven and NOT a
> calendar. Built as a boost it fits perfectly; built as a schedule it would make the decay
> engine decorative. Do not start this before Phase 7.

```
Read cleaning-app-spec.md §1 (decay, not a calendar) and §4 (the decay engine). Build Phase 8:
an optional preferred-day priority boost. Phase 7's test suite must exist first.

THE DESIGN CONSTRAINT, read this before anything else: this is a BOOST, not a SCHEDULE.
Tada has no due dates by design — a task's priority is a gradient driven by time since it was
last done. A hard day-of-week schedule would put a calendar in direct conflict with the decay
engine, and there would be no good answer to "she did laundry on Wednesday, does Saturday
still fire?" With a boost there is: the task decays normally all week, so by Saturday it's
fresh and simply doesn't surface. Nothing ever becomes "overdue" or "missed".

Build:

1. MIGRATION (additive): a nullable `preferred_day` on tasks — small integer, Python
   `weekday()` convention (Monday = 0 ... Sunday = 6), null meaning no preference. Null must
   remain the default and the overwhelmingly common case.

2. THE BOOST, in `rank_tasks`. Her rule exactly: boost on the preferred day AND on the
   following day as a grace day, then nothing until the preferred day comes round again. For
   laundry set to Saturday: boosted Saturday, boosted Sunday if it didn't happen, then quiet
   until the next Saturday. "Today" means her local timezone day, not UTC.
   - Implement as a strong ADDITIVE boost to the priority score — NOT a hard pin to position
     one. A pin would bury a genuinely neglected task behind laundry, and it gives no ordering
     at all between two tasks that share a preferred day. The boost should be large enough
     that laundry leads on Saturday in normal conditions, while something truly neglected can
     still edge above it.
   - Multiple tasks may share a preferred day; they boost equally and order among themselves
     by normal decay priority.
   - The task decays normally throughout — the boost changes ranking only, never
     `dirtiness_ratio`, `last_done_at`, or any band.
   - Missing the preferred day carries NO penalty and produces no overdue state, no different
     copy, and no notification.

3. UI in the task form: an optional day-of-week picker, clearly optional and clearly not a
   deadline. Copy should read like a preference, e.g. "Usually a Saturday job" — never
   "Due Saturday" or "Scheduled for Saturday".

4. EXTEND THE PHASE 7 TESTS to cover the boost: on the preferred day, on the grace day, on
   an ordinary day, two tasks sharing a preferred day, and the case where a badly neglected
   task without a preferred day still outranks a boosted fresh one.

Follow SPEC §8 conventions. When done, summarize what you built and confirm the decay engine's
existing tests still pass unchanged.
```

**Phase 8 is done when:** laundry leads the list on Saturday and again on Sunday if it didn't
happen, then waits quietly for next Saturday — and nothing anywhere in the app has become a
deadline.

---

---

## Working notes

- Test on her actual phone between phases. The design hinges on the phone feel, and three of
  the bugs in Phase 4.5 were only visible there.
- If a feature starts creeping in scope, park it and finish the phase first.
- Keep the reward system encouraging-only. If any copy or mechanic starts to feel like it's
  nagging or shaming, cut it — that betrays the core design.
- The home screen is the product. Phase 5 adds exactly one element to it; nothing else in
  these phases may add another.
- Every build prompt here carries an explicit feature checklist on purpose. The badge system
  went unbuilt for four phases because it lived in the spec but never in a prompt.

  # Tada — Build Prompt: Phase 9

>
> Came out of Maryann using the app daily after Phases 4.5–8 shipped: she wants to undo a task
> she marked complete by mistake. It's the most on-brand feature request the app has had — the
> whole premise is that mistakes and gaps are fine, and this applies that idea to the app's own
> primary interaction.
>
> Safe to build now specifically *because* Phase 7 landed. It touches the engine's anchor field,
> and the test suite will catch a regression.

---

## Phase 9 — Undo a completion

```
Read cleaning-app-spec.md §4 (the decay engine) and §5 (no-guilt design). Build Phase 9: undo
for an accidentally completed task.

THE CORE DESIGN DECISION, read this first: undo reverses the DECAY STATE ONLY. It restores
`last_done_at` and removes the CompletionLog row. It does NOT touch streaks, and it does NOT
revoke badges. Streaks only ever go up.

The reasoning, so you don't "improve" on it:
- Badges are already earned-once-never-revoked by design (SPEC §5), so that part is settled.
- For streaks, compare the two failure modes. If undo leaves the streak alone, she keeps credit
  for a day she technically didn't earn — and nobody is auditing. If undo reverses it, one
  mis-tap plus a correction can destroy a 30-day streak. That asymmetry is not close.
- Reversing a streak correctly is also genuinely hard: you'd have to know whether other
  completions happened that day, whether THIS completion caused the increment, and whether a
  grace day was involved.
- It sidesteps multi-user entirely — if one person completes something and another undoes it,
  there's no question about whose streak moved.

SCOPE: today's completions only. Anything older is already handled by the editable last-done
date from Phase 4.6. Do NOT build a general-purpose completion history editor or a time
machine — a short window plus the existing escape hatch covers every real case.

Build:

1. MIGRATION (additive, follows the latest): add a nullable `previous_last_done_at` datetime
   column to the completion log table.
   Why store it rather than derive it: the previous value COULD be read from the prior
   CompletionLog row, but that breaks in a real case — Phase 4.6's editable last-done date
   deliberately sets `last_done_at` WITHOUT writing a log row. So if she corrects a date, then
   completes by mistake, then undoes, a log-derived restore would silently discard her
   correction. Storing the value makes undo exact and removes all reasoning about log ordering.

2. CAPTURE THE PREVIOUS VALUE. Update `scheduling.complete_task()` to write the task's existing
   `last_done_at` into `previous_last_done_at` on the new log row before overwriting it. This is
   the only edit to existing engine code in this phase — keep it minimal and leave everything
   else in that function exactly as it is.
   Note: for a first-ever completion the previous value is legitimately NULL, and undo must
   restore the task to never-done. That is correct behavior, not a bug.
   Known edge, acceptable: CompletionLog rows created BEFORE this migration will have NULL in
   the new column, indistinguishable from a genuine never-done. Since undo is only offered on
   today's completions, the exposure is the first day after deploy, and the consequence is mild
   and self-correcting (the task reads as never-done, surfaces high, and she can fix it with the
   Phase 4.6 date editor). Don't engineer around this.

3. THE REVERSE FUNCTION, in backend/app/services/scheduling.py alongside `complete_task()`.
   Given a completion log row it should:
   - restore `task.last_done_at` from `previous_last_done_at`, preserving NULL as NULL
   - delete the log row
   - leave `current_streak`, `longest_streak`, and `last_active_date` untouched
   - leave earned badges untouched
   - leave `snoozed_until` cleared — completion cleared it, and undo does not bring a snooze
     back. Restoring a snooze on undo would be surprising, and she can snooze again in a tap.
   - take an injectable `now` like every other function in this module
   - refuse anything not completed today, and return a clear error the UI can handle
   Permissions: an owner can undo any of today's completions; a kid can undo only their own.
   This is a correction, not a dispute — don't build anything more elaborate.

4. UNDO IN THE COMPLETION TOAST. This is the main use case, since an accidental tap gets
   noticed immediately.
   - Appears after the celebration, and must NOT compete with it. Let the burst have its
     moment, then a small, low-contrast "Undo" that lingers a few seconds and fades.
   - Label it exactly "Undo". Nothing that reads as an accusation — no "Oops", no "Mistake?",
     no "Did you mean to do that?".
   - NO confirmation dialog. A confirm on an undo is absurd; undo IS the safety net.
   - CRITICAL: in a focus session the toast must not gate or delay advancing to the next task.
     She should be able to keep going immediately and have it fade on its own.

5. UNDO PER ROW IN DONE TODAY. Nearly free, since that view already lists today's completions
   from the log, and it catches the other real case: "I marked the wrong task."
   - A small, secondary affordance per row — not a button competing with the content.
   - On undo the row leaves the list. The streak display must NOT change.
   - If it was the only completion today, the view returns to its normal warm empty state.
     The empty copy must not acknowledge the undo — no "you undid everything", no running
     total that went down. It reads exactly as it would on a quiet morning.

6. LEAVE GUEST MODE ALONE. Don't add undo to the guest-mode surface. It's a deliberately
   minimal screen for a houseguest, and an undo affordance there is confusing rather than kind.

7. EXTEND THE PHASE 7 TEST SUITE:
   - undo restores the exact previous `last_done_at`
   - undo of a first-ever completion restores never-done (NULL preserved)
   - undo deletes the log row
   - undo leaves `current_streak`, `longest_streak`, and `last_active_date` unchanged
   - undo does not revoke a badge earned by the completion it reverses
   - a snooze cleared by completion stays cleared after undo
   - ROUND TRIP: capture a task's dirtiness ratio and band, complete it, undo it, and assert
     the ratio and band match the original exactly. This is the test that matters most.
   - undo is refused for a completion from a previous day

Follow SPEC §8 conventions. When done, summarize what you built and confirm the existing decay
engine tests still pass unchanged.
```

**Phase 9 is done when:** she can tap Undo right after a mis-tap or from Done Today, the task
returns to exactly the priority it had before, her streak doesn't budge, and nothing in the
copy suggests she did anything wrong.


## Deferred and cut

**Notification badge icon — deferred (on the backburner, not forgotten).** The status-bar icon
renders as a blank square. Diagnosed: `frontend/public/sw.js` sets `badge: "/icons/icon-192.png"`,
but Android masks the badge and derives a silhouette from the alpha channel alone. The 192 icon
is `"purpose": "any maskable"`, so it's fully opaque and the silhouette is a square. The fix is
a dedicated 96×96 monochrome white-on-transparent PNG, then pointing `badge` at it. Also worth
checking whether `/icons/icon-192.png` is still a Phase 0 placeholder. Explicitly excluded from
Phase 4.5.

**Third effort tier — cut.** She felt there was a middle ground between Quick Wins and Deep
Clean but couldn't name an example, and said she can go without. It's also the most expensive
item on the list: `effort` is a two-value enum threaded through the model, roughly 100 seeded
starter tasks, guest mode's `effort == "quick"` filter, the task form, and the home chips.
Worth noting *why* it feels wrong to her — effort is about energy but the data conflates it
with duration (a 20-minute "fold laundry" is tagged quick; a 10-minute washer run is tagged
deep). Revisit only with three concrete examples in hand, and migrate by rule rather than
re-tagging by hand.

**Budget app integration — deferred by design.** Phase 6 adds per-item prices, which is the
foundation. When the budget app exists, model the link on the MealGenie integration: one-way
push, shared API key from env, upsert on the receiving end, failures swallowed. Expose the
external line-item endpoint in the budget app's own Phase 1 so it's a design input rather than
a retrofit. Keep the budget app owning budgets and spend, and Tada owning items and checkoffs —
a nullable `budget_category_id` on a list is the entire link. Avoid two-way sync.

**Already built — do not rebuild.** Task assignment and the exclusion of delegated tasks from
her surfaces work today (`for_user_id=current_user.id` is passed in `/focus` and
`/sessions/build`; tasks assigned to someone else are already filtered out). Shared multi-user
access also already works — no data is scoped per user and `require_owner` only checks role,
so a second owner account sees everything she sees.

**Timer — deferred.** The in-app timer for tasks is postponed. It may be revisited once the core task management and undo functionality are stable, as it is not critical to the immediate workflow and adds complexity to the UI. **Currently implemented as a notification only.**