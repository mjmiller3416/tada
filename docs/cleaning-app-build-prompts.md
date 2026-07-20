# Tada — Build Prompts
---

✅ ## Phase 0 — Foundation & scaffold

```
Read SPEC.md fully before starting. We're building Phase 0 only: the deployed
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

Follow the coding conventions in SPEC §8. When done, give me: the file structure,
the env vars I need to set on Railway, and step-by-step instructions to (a) install
the PWA on an Android phone, (b) grant notification permission, and (c) trigger and
receive the test push.

Do NOT build any cleaning features yet — only the foundation above.
```

✅ **Phase 0 is done when:** the app is deployed on Railway, the owner can log in, the PWA installs on the phone, and a manually triggered test push actually arrives on the phone. Then remove/disable the temporary test-push trigger.

---

✅ ## Phase 0.5 — Design foundation

```
Read SPEC.md, especially section 5 (design system). Build the design foundation BEFORE
any feature UI, so every later phase composes the same components and Tada looks cohesive
throughout. Do NOT build feature screens here.

Build:
1. Design tokens as the single source of truth — CSS variables (or theme config): the
   palette (rose coral #E15B54 for primary actions, teal #1D9E75 for Done/success,
   wisteria purple #7E57B2 for celebration/reward moments, plus the
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

✅ **Phase 0.5 is done when:** the design tokens exist as the single source of truth, the core React primitives render correctly on the preview page, and the look matches the bright/playful direction — so feature phases can compose them. (You can also restyle the Phase 0 login here.)

---

## Phase 1 — The spine (core app)

```
Read SPEC.md. Build Phase 1 on top of the Phase 0 foundation: the complete core app.

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

Apply the design system in SPEC §5 precisely: rose coral (#E15B54) primary actions, teal
(#1D9E75) for Done, cheerful color-coded chips, rounded friendly shapes, warm
first-name no-guilt copy. Phone = one-thing-at-a-time; Chromebook = full lists/editing.
Follow SPEC §8 conventions and summarize what you built when done.
```

**Phase 1 is done when:** she can set up her home on the Chromebook, get an auto-generated schedule, and on her phone tap "I have 15 minutes" (or pick a room) and be guided through tasks one at a time with real reminders firing.

---

## Phase 2 — People, supplies, maintenance

```
Read SPEC.md. Build Phase 2 on top of Phase 1.

Build:
1. Multi-user (SPEC §6): kids get their own logins (role "kid") with basic
   functionality only — see their assigned and claimable chores and check them off.
   On a kid's completion, send a push notification to the owner. Tasks can be assigned
   to a specific member or left open to claim. NO points, rewards, or gamification for
   the kids' chores. (The owner's own login and full functionality already exist.)
2. Supplies (SPEC §6): a Supply inventory with manual status only (in_stock / low /
   out — never auto-decremented). Link tasks to the supplies they use. When a task
   whose linked supply is low/out surfaces in a session, flag it inline. Anything
   low/out flows onto a shopping list the owner can check off.
3. Maintenance (SPEC §6): support category "maintenance" on tasks with long cadences,
   surfaced in their own section/filter so they don't clutter daily cleaning.

Keep the kid experience simple and role-restricted. Follow SPEC §5 (design/voice) and
§8 (conventions). Summarize what you built when done.
```

**Phase 2 is done when:** a kid can log in, check off a chore, and the owner gets a notification; supplies can be marked low/out and appear on a shopping list; maintenance tasks live in their own section.

---

## Phase 3 — Overlays

```
Read SPEC.md. Build Phase 3 on top of Phase 2. These are opt-in overlays on the core —
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

---

## Working notes

- After each phase, do a quick pass on her actual phone before starting the next — the whole design hinges on the phone feel.
- If a feature starts creeping in scope (the way MealGenie did), park it and finish the phase first.
- Keep the reward system encouraging-only. If any copy or mechanic starts to feel like it's nagging or shaming, cut it — that betrays the core design.