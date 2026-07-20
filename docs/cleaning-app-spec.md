# Tada — Project Spec

> Persistent project context for Claude CLI. Commit this to the repo root (e.g. as `SPEC.md` or fold into `CLAUDE.md`) so every build session has the full picture. Build prompts live in a separate file and reference this spec by section.

---

## 1. Overview

**Tada** is a private, personal cleaning & home-task app for one household. Not a public product — no marketing, no multi-tenant concerns beyond this one family. Two kinds of users: one **owner** (the primary user, "the parent") and a few **kids**.

**The core philosophy — three ideas that drive every decision:**

1. **Decay, not a calendar.** Tasks don't have fixed due dates. Each task slowly gets "dirtier" over time based on how long since it was actually last done. Cleaning resets it. Priority is a gradient, not a binary overdue flag.
2. **Guide, don't list.** The owner knows *what* needs doing — being shown a long list is what causes paralysis ("I don't even know where to start"). On the phone, the app hands her **one task at a time**, never a wall. Lists exist only on the Chromebook, where she's *planning*, not *doing*.
3. **Bright, warm, forgiving.** Cheerful and encouraging, celebration in the small moments, and never guilt-inducing. Missing a day or snoozing a task is fine and is never punished.

**The device split is the design split:**

- **Chromebook = planning mode.** Full lists, everything editable. Setup, configuration, and reorganizing all happen here.
- **Phone (Android) = doing mode.** One clear next action at a time. This is the daily surface.

---

## 2. Tech stack (final)

- **Frontend:** Next.js, built as an **installable PWA** (web app manifest + service worker). Installable to the Android home screen; also usable in the Chromebook browser at the same URL.
- **Backend:** **FastAPI** (Python).
- **Database:** **Railway Postgres**.
- **Hosting:** everything on **Railway** (alongside two existing apps). Backend, frontend, DB, and the cron service are all Railway services.
- **Notifications:** **Web Push** using the standard VAPID protocol. Backend sends pushes with **`pywebpush`**. No native app, no FCM integration directly — the browser's push service handles delivery. Works reliably on Android Chrome when the PWA is installed and notification permission is granted.
- **Reminder engine:** a **Railway cron job running every minute** that queries reminders due now and sends the corresponding pushes. Simple, restart-safe, easy to reason about. No in-process scheduler state.
- **Auth:** a simple **login** with a **long-lived session (or PIN)** so the owner isn't re-authenticating constantly on her phone. **Do NOT use IP whitelisting** — she uses the app all day on cellular and other networks, and an IP gate would lock her out. The login is sufficient access control.
- **Multi-user / role-aware from day one:** even though only the owner logs in during Phase 1, build the `User` model with a `role` field (`owner` / `kid`) from the start so adding kids in Phase 2 is filling in an existing model, not a retrofit.

---

## 3. Core data model

Build the schema to support all phases from the start where cheap (so migrations are additive). Core entities:

```
User
  id, name, username/email, password_hash
  role: "owner" | "kid"
  current_streak, longest_streak, last_active_date   # streak tracking (forgiving — see §5)
  created_at

PushSubscription            # one user can have several (phone + chromebook)
  id, user_id -> User
  endpoint, p256dh, auth    # the Web Push subscription keys
  created_at

Room
  id, name, zone_id -> Zone (nullable), sort_order

Zone                        # FlyLady overlay (see §6). Optional feature; rooms map into zones.
  id, name, week_of_month (1..5), sort_order

Task                        # the central entity
  id, name
  room_id -> Room (nullable)
  category: "cleaning" | "maintenance"
  cadence_days: int          # THE DECAY RATE. Tier presets map to values; custom = any int.
  estimated_minutes: int
  effort: "quick" | "deep"   # two levels only
  guest_facing: bool         # used by guest/Chaos mode
  last_done_at: timestamp (nullable)   # null = never done
  assignee_id -> User (nullable)
  is_active: bool
  notes (nullable), created_at

TaskSupply                  # many-to-many Task <-> Supply
  task_id -> Task, supply_id -> Supply

Supply
  id, name
  status: "in_stock" | "low" | "out"    # MANUAL only — never auto-decremented
  last_pushed_at: timestamp (nullable)   # when last pushed to MealGenie's list (dedupe)
  created_at
# No shopping-list entity in Tada — low/out supplies are pushed to MealGenie's list (see §6).

CompletionLog               # history; feeds streaks, badges, and kid-completion notifications
  id, task_id -> Task
  completed_by -> User
  completed_at
  source: "focus_session" | "direct" | "guest_mode" | "zone" | "campaign"

Reminder                    # the cron polls this table
  id, user_id -> User, task_id -> Task (nullable)
  title, body
  scheduled_for: timestamp
  recurrence_rule (nullable)     # for repeating nudges
  last_sent_at (nullable), active: bool

Campaign                    # seasonal campaigns (overlay)
  id, name, season, start_date, end_date, active
CampaignTask
  campaign_id -> Campaign, task_id -> Task, done: bool

Badge                       # achievement definitions
  id, key, name, description, icon, criteria
UserBadge
  user_id -> User, badge_id -> Badge, earned_at

Setting                     # per-user config (daily focus count, reminder times, overlays on/off)
  id, user_id -> User (nullable = app-wide), key, value
```

Cadence tier presets (map to `cadence_days`): daily = 1, weekly = 7, monthly = 30, seasonal = 91, annual = 365. "Custom" = any integer.

---

## 4. The decay engine (the heart — build this well)

Everything prioritization-related reads one computed signal.

**Dirtiness ratio** for a task:

```
ratio = (now - last_done_at) / cadence_days       # in matching units
# last_done_at is null (never done)  -> treat as high priority (ratio >= 1.5)
```

- `ratio < 0.5` → fresh (green)
- `0.5 ≤ ratio < 0.9` → aging (yellow)
- `0.9 ≤ ratio < 1.2` → due (orange)
- `ratio ≥ 1.2` → overdue (red)

**Priority ranking** (used by every "what should I do" feature): sort candidate tasks by `ratio` descending. Tie-breaks: overdue before due, then higher `ratio`, then longer since `last_done_at`. Daily-cadence tasks should be weighted so they reliably surface each day.

**Completion** sets `last_done_at = now`, which drops `ratio` to 0 and restarts the curve. Write a `CompletionLog` row on every completion.

**Room aggregate dirtiness** (for room view): roughly the max/average `ratio` across that room's active tasks, mapped to the same color bands.

Keep the decay/ranking logic in a clearly separated, documented service module (e.g. `services/scheduling.py`) — it's the core of the app and will be read and tuned often.

---

## 5. UX principles & design system

### Interaction model — the focus session

The signature interaction. Triggered by "I have X minutes," or by picking a room, or by "this week's zone."

1. Compute the priority ranking behind the scenes, filtered by the trigger (time budget, room, zone, effort, or `guest_facing`).
2. For a time budget: greedily pick tasks whose `estimated_minutes` cumulatively fit the budget.
3. **Present ONE task at a time** as a single card: room tag, task name (large), time estimate, a big **Done** button, and a quiet **Skip for now**.
4. Show only a **small progress signal** — three dots / "2 of 3" / a shrinking timer — so she feels momentum and a finish line, but never sees the full list.
5. **Done** → log completion, reset the task, a brief celebration (a pop / confetti), advance to the next card. **Skip** → advance with no penalty, no logging.
6. When the budget is spent (or no candidates remain) → a session-complete celebration + badge check.

It's a cleaning *coach*, not a to-do list. Picking a room or zone launches the same one-at-a-time flow scoped to it — never a task dump.

### Visual direction — bright, playful, but not busy

- **Primary action color: coral** (`#D85A30`). The main "go" button (e.g. "I have 15 minutes").
- **Success / Done: teal-green** (`#1D9E75`).
- **Category / shortcut chips:** soft, cheerful color-coded tints (light blue, purple, green, amber). Colorful and inviting, but restrained enough that the UI itself never adds to the overwhelm.
- Rounded, friendly shapes: cards ~12px radius, buttons ~14px, pills fully rounded. Generous whitespace. A friendly rounded sans-serif. Two font weights only.
- **Large touch targets, one-handed phone use, minimal typing on the phone.** Heavy input (adding tasks, editing schedules) is a Chromebook activity.

### Motion & voice — the reward is in the doing

- Satisfying micro-interactions: a pop when Done is tapped, confetti on session completion, smooth card transitions.
- Warm, first-name, encouraging copy. **Never guilt.** "Nice work," not "You're behind." A snoozed or skipped task is met with grace, never a scolding. This voice runs through *everything* — it's core, not decoration.

### Gamification — badges, not levels

- **Badges / achievements only.** No XP, no levels. Collectible, positive-only — you *earn* them, you can never *lose* one. Examples: first task done, 7-day streak, completed a full zone week, a guest-mode rescue, first seasonal campaign finished, 100 tasks, early bird.
- **Streaks must be forgiving.** A streak flame is fine, but a broken streak must never sting. Build in grace days / an auto-applied "freeze" so a missed day doesn't wipe progress. The reward system is strictly *encouraging*, never *punishing* — consistent with the no-guilt voice above.

---

## 6. Feature reference

Most features are lenses or modes over the §3 model + §4 engine — not separate systems.

**Core scheduling (Phase 1).** The decay engine (§4). Cadence = decay rate, with tier presets + custom intervals. Completion resets the curve.

**Rooms & task views (Phase 1).** Two ways to browse the same tasks: a **Room view** (grouped by room, each showing aggregate dirtiness) and a **Task/global view** (one flat, sortable, filterable list across the home — by dirtiness, room, effort, category). Both are planning-surface (Chromebook) tools.

**Cadence tiers + custom (Phase 1).** Presets (daily→annual) and arbitrary custom intervals; just how `cadence_days` gets set on a task.

**Onboarding wizard (Phase 1, Chromebook-first).** Capture a home profile — rooms (and zone mapping if zones are enabled), household members, pets/kids context. Then **auto-generate a starter task list** with sensible default cadences, time, and effort per room so she gets a working schedule in a couple of minutes, then edits from there. Also where she enables/disables the optional overlays (zones, campaigns) and sets up supplies.

**Daily-use lenses (Phase 1) — all read the one priority ranking:**
- **Daily focus (1–3 tasks).** The calm home screen: the top 1–3 tasks by priority, not a wall. Backlog is one tap away, not the default. `N` configurable (default 3).
- **"I have X minutes" mode.** Time-budget filter (default 15; let her set 5/30/45). Greedy fill by priority.
- **Energy filter.** Weight by `effort`: low-energy surfaces quick wins, deep-clean day surfaces big tasks. Stacks with the other two.
- **Decay-aware snooze.** Defers the *reminder* (later today / tomorrow / a few days) **without** resetting `last_done_at` — the task keeps aging quietly and resurfaces, but she isn't nagged now and nothing is falsely marked done. No guilt language.

**Supplies (Phase 2).** A small inventory: each supply is `in_stock` / `low` / `out`, set **manually** (one tap — no auto-decrement, which is guesswork that drifts). Tasks link to the supplies they use. When a task whose linked supply is `low`/`out` surfaces, flag it inline ("heads up — you're low on floor cleaner"). **Tada has no shopping list of its own** — when a supply is marked `low`/`out`, Tada pushes it into **MealGenie's existing shopping list** (which the owner already uses and loves) via MealGenie's API. One-way push; deduped via `last_pushed_at` so nothing is added twice; each item tagged (source `tada`, category `household`) so supplies stay distinguishable from groceries. The MealGenie-side changes are specified in the build-prompts file.

**Multi-user assign/claim (Phase 2).** Kids get their **own logins** (role `kid`) with **basic functionality**: see their assigned/claimable chores, check them off. **On completion, notify the owner** (via push). Tasks can be assigned to a member or left open to claim. **No rewards, points, or gamification for the kids' chores** — purely assignment + completion + notification.

**Maintenance tasks (Phase 2).** Same engine, `category = maintenance`, long cadences (HVAC filters, smoke/CO batteries, gutters, descaling). Give them their own section/filter so they don't clutter daily cleaning.

**Guest / "Chaos Cleaning" mode (Phase 3).** The "I have X minutes" lens pointed at **guest-facing areas only.** Trigger: "company in [time]." Filter to `guest_facing = true` tasks, fill the time budget by impact — a fast, high-visibility punch list, skipping deep/hidden tasks. Runs as a focus session.

**Seasonal campaigns (Phase 3).** Episodic bundled projects (e.g. "Spring Cleaning"): a named `Campaign` grouping tasks with a date window and a progress rollup. Activate it → the app surfaces the campaign's task set, spread over days, tracking % complete. Distinct from everyday decay tasks. An opt-in overlay.

**FlyLady zone cleaning (Phase 3).** An **opt-in overlay**, not a replacement for the decay model. FlyLady divides the home into five zones, each getting focused ~15-min/day detailed cleaning for one week of the month:
- **Zone 1** — entrance, front porch, dining room — the first few days of the month
- **Zone 2** — kitchen — first full week
- **Zone 3** — main bathroom + one other room — second full week
- **Zone 4** — master bedroom, bath, and closet — third full week
- **Zone 5** — living room / family room — the last few days (zones 1 and 5 often share a calendar week)

Implement: a zone→room mapping (defaulting to the five above but fully editable in onboarding — most homes differ), plus a rule that derives the *current* zone from today's date. A "This week's zone" view surfaces that zone's tasks as a focus session. The decay engine keeps driving everyday upkeep; the zone overlay adds a rotating deep-clean focus on top. Seed each zone's task list in FlyLady's structure, editable by her.

**Badges (introduced alongside the reward moments; core definitions can seed in Phase 1, expanded later).** See §5.

---

## 7. Phase map

- **Phase 0 — Foundation.** Scaffold + deploy the empty shell; prove push + auth + cron end-to-end.
- **Phase 0.5 — Design foundation.** Establish design tokens (the §5 palette/type/spacing/motion) as the single source of truth and a core set of React primitives (Button, Card, Chip, the focus/task card, app shell, celebration) on a preview page — before any feature UI, so every later phase composes the same components. Grow the library per phase from the tokens.
- **Phase 1 — The spine.** Decay engine, rooms, both views, cadence, onboarding, daily focus, "I have X minutes," energy filter, snooze, reminders. A complete, useful app.
- **Phase 2 — People, supplies, maintenance.** Kid logins + check-off + owner notifications, assign/claim, supply inventory (low/out items push into MealGenie's shopping list), maintenance category.
- **Phase 3 — Overlays.** Guest/Chaos mode, seasonal campaigns, FlyLady zones.

Build one phase at a time; verify each works before starting the next. Detailed per-phase prompts are in the build-prompts file.

---

## 8. Coding conventions (for Claude CLI)

- **Write complete files/modules, not fragments.** When adding or changing a function, output the whole function.
- **Docstrings and comments** on non-trivial logic — especially the decay/ranking/session code.
- **Separate concerns into dedicated modules:** keep the data model, business logic (scheduling/decay, session building, badge evaluation), and API routes distinct. Put reusable backend helpers in clearly named service/helper modules; keep frontend logic in well-organized hooks/components.
- **Additive migrations.** Build the schema to anticipate later phases so migrations don't require rework.
- **At the end of each phase, summarize what was built** — files created/changed and how to run/verify it.
- **Design system first (Phase 0.5).** Define the §5 tokens (palette, type, spacing, radii, motion) as the single source of truth — CSS variables or theme config — and build the core React primitives that consume them (Button, Card, Chip, focus/task card, app shell, celebration). Every later phase composes these primitives and adds new components only from the same tokens, so the look stays cohesive across all phases.
- Match the design system in §5 precisely: the focus-session interaction, the coral/teal palette, rounded friendly shapes, warm no-guilt copy, and badges-not-levels.