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
```

**Phase 4 is done when:** Maryann can create a list from a pre-filled template, see it as a full grouped checklist with progress, check items off, run more than one list at once, archive a finished list, and (optionally) get a countdown reminder before an event date — all without any interaction with the cleaning/decay side of the app.

---

## Working notes

- After each phase, do a quick pass on her actual phone before starting the next — the whole design hinges on the phone feel.
- If a feature starts creeping in scope (the way MealGenie did), park it and finish the phase first.
- Keep the reward system encouraging-only. If any copy or mechanic starts to feel like it's nagging or shaming, cut it — that betrays the core design.