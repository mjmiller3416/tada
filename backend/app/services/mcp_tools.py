"""The ChatGPT connector's tools: one per thing a household member can
do in Tada.

Every tool is a thin, declarative wrapper over one real Tada route: the
MCP endpoint (routers/mcp.py) turns a tool call into an in-process HTTP
request to that route, signed in as the member who approved the
connection. So validation, owner-only checks, decay maths, pushes to the
shopping list, badge awards and every other side effect are exactly the
app's own — no tool touches the database itself.

Rules for adding a tool (tests/test_mcp_tools.py enforces the first two):

- every user-facing route under /api needs a tool (or a reason in
  `LEFT_OUT`), and every tool's (method, path) must be a real route;
- path parameters are named exactly as in the route ("{task_id}");
- arguments listed in `query` go on the query string, the rest of a
  POST/PUT/PATCH's arguments become the JSON body;
- annotate honestly: reads are read_only, deletes destructive, and
  open_world only for tools that reach outside Tada.
"""

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------


def _int(description: str, minimum: int | None = None, maximum: int | None = None) -> dict:
    schema: dict = {"type": "integer", "description": description}
    if minimum is not None:
        schema["minimum"] = minimum
    if maximum is not None:
        schema["maximum"] = maximum
    return schema


def _str(
    description: str,
    enum: list[str] | None = None,
    min_length: int | None = None,
    max_length: int | None = None,
) -> dict:
    schema: dict = {"type": "string", "description": description}
    if enum:
        schema["enum"] = enum
    if min_length is not None:
        schema["minLength"] = min_length
    if max_length is not None:
        schema["maxLength"] = max_length
    return schema


def _bool(description: str) -> dict:
    return {"type": "boolean", "description": description}


def _ids(description: str) -> dict:
    return {"type": "array", "items": {"type": "integer"}, "description": description}


def _date(description: str) -> dict:
    return {"type": "string", "format": "date", "description": f"{description} (YYYY-MM-DD)."}


def _money(description: str) -> dict:
    return {
        "type": "string",
        "pattern": r"^\d{1,8}(\.\d{1,2})?$",
        "description": f"{description} Dollars as a string, e.g. \"12.50\".",
    }


EFFORT = ["quick", "deep"]
TASK_TYPES = ["routine", "weekly_blessing", "zone", "maintenance", "project"]
SOURCES = ["direct", "focus_session", "guest_mode", "zone", "campaign"]
ROOM_TYPES = [
    "kitchen", "bathroom", "bedroom", "living_room", "dining_room", "office",
    "laundry", "entryway", "hallway", "playroom", "garage", "basement", "other",
]

TASK_TYPE_HELP = (
    "Which clock schedules it: routine (everyday upkeep, decay), weekly_blessing "
    "(whole-home weekly jobs like vacuuming), zone (a 5-15 minute detail mission for "
    "its room's FlyLady zone week), maintenance (long-cadence home maintenance like "
    "HVAC filters), project (one-off, never scheduled automatically)."
)


# ---------------------------------------------------------------------------
# The tool type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    method: str
    path: str
    properties: dict = field(default_factory=dict)
    required: tuple[str, ...] = ()
    #: Argument names sent on the query string instead of the body.
    query: tuple[str, ...] = ()
    read_only: bool = False
    destructive: bool = False
    idempotent: bool = False
    open_world: bool = False
    #: Optional post-processing of the route's JSON, given the arguments.
    shape: str | None = None
    #: Composite tools (no single route) name every route they read.
    routes: tuple[tuple[str, str], ...] = ()

    @property
    def title(self) -> str:
        return self.name.replace("_", " ").capitalize()

    def definition(self) -> dict:
        """The tools/list entry."""
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": {
                "type": "object",
                "properties": self.properties,
                "required": list(self.required),
                "additionalProperties": False,
            },
            "annotations": {
                "title": self.title,
                "readOnlyHint": self.read_only,
                "destructiveHint": self.destructive,
                "idempotentHint": self.idempotent or self.read_only,
                "openWorldHint": self.open_world,
            },
        }

    def covered_routes(self) -> tuple[tuple[str, str], ...]:
        return self.routes or ((self.method, self.path),)


def _read(name, description, path, properties=None, required=(), query=(), shape=None) -> Tool:
    return Tool(
        name=name,
        description=description,
        method="GET",
        path=path,
        properties=properties or {},
        required=tuple(required),
        query=tuple(query),
        read_only=True,
        shape=shape,
    )


# ---------------------------------------------------------------------------
# Common argument blocks
# ---------------------------------------------------------------------------

TASK_ID = _int("The task's id, from list_tasks, get_daily_focus or get_my_chores.")
ROOM_ID = _int("The room's id, from list_rooms.")
SUPPLY_ID = _int("The supply's id, from list_supplies.")
MEMBER_ID = _int("The household member's id, from list_members.")
ZONE_ID = _int("The zone's id, from list_zones.")
CAMPAIGN_ID = _int("The campaign's id, from list_campaigns.")
LIST_ID = _int("The list's id, from list_lists (or list_list_templates for templates).")
SECTION_ID = _int("The section's id, from get_list.")
ITEM_ID = _int("The item's id, from get_list.")
TIMER_ID = _int("The timer's id, returned by start_session_timer.")

TASK_FIELDS = {
    "room_id": _int("Room it belongs to (from list_rooms)."),
    "task_type": _str(TASK_TYPE_HELP, enum=TASK_TYPES),
    "cadence_days": _int(
        "How often it should be done, in days — the decay rate. Presets: daily 1, "
        "weekly 7, monthly 30, seasonal 91, annual 365; any whole number works.",
        1,
        730,
    ),
    "estimated_minutes": _int("How long it takes, in minutes.", 1, 480),
    "effort": _str("quick (light) or deep (a bigger job).", enum=EFFORT),
    "guest_facing": _bool("True if it matters when company is coming (used by guest mode)."),
    "assignee_id": _int("Household member it's assigned to (from list_members)."),
    "claimable": _bool("True to leave it up for grabs so a kid can claim it."),
    "supply_ids": _ids("Supplies this task uses (ids from list_supplies). Replaces the whole set."),
    "notes": _str("Free-text notes."),
    "preferred_day": _int(
        "Usual day for it, 0=Monday … 6=Sunday. A gentle ranking boost on that day, never a deadline.",
        0,
        6,
    ),
}

SESSION_FIELDS = {
    "minutes": _int("Time budget in minutes (\"I have X minutes\").", 5, 240),
    "room_id": _int("Only tasks in this room (from list_rooms)."),
    "effort": _str("quick for a low-energy session, deep for a big-clean day.", enum=EFFORT),
    "zone_id": _int("Only this FlyLady zone's tasks (from list_zones)."),
    "zone_missions": _bool("True for a zone-missions-only session (\"this week's zone\")."),
    "campaign_id": _int("Build today's slice of this seasonal campaign instead (from list_campaigns)."),
    "guest": _bool("True for guest/Chaos mode: guest-facing quick wins only (\"company's coming\")."),
    "exclude_task_ids": _ids("Task ids to leave out, e.g. ones already in the session."),
}


# ---------------------------------------------------------------------------
# The catalog
# ---------------------------------------------------------------------------

TOOLS: list[Tool] = [
    # ---- Overview -------------------------------------------------------
    Tool(
        name="get_overview",
        description=(
            "Start here. A snapshot of the household right now: who you're signed in as, "
            "today's focus tasks, what's been done today, rooms needing attention, supplies "
            "running low, and settings like vacation mode. For a kid account, their chores."
        ),
        method="GET",
        path="",
        read_only=True,
        routes=(
            ("GET", "/api/auth/me"),
            ("GET", "/api/focus"),
            ("GET", "/api/done-today"),
            ("GET", "/api/rooms"),
            ("GET", "/api/supplies"),
            ("GET", "/api/settings"),
            ("GET", "/api/chores"),
        ),
    ),
    _read(
        "who_am_i",
        "Which household member this connection acts as, and whether they're an adult (owner) or a kid.",
        "/api/auth/me",
    ),
    _read(
        "get_daily_focus",
        "The 1–3 tasks Tada suggests doing next, dirtiest first (the home screen). "
        "Use when asked what to clean now.",
        "/api/focus",
        {"effort": _str("quick to favour light tasks, deep for big jobs.", enum=EFFORT)},
        query=("effort",),
    ),
    _read(
        "get_done_today",
        "Everything the household completed today (in the household's time zone), who did it, "
        "plus the current streak and earned badges. Each completion's id can be passed to undo_completion.",
        "/api/done-today",
    ),
    _read(
        "get_my_chores",
        "The signed-in member's assigned chores plus chores up for grabs (the kids' view). "
        "Works for adults and kids.",
        "/api/chores",
    ),
    # ---- Rooms ----------------------------------------------------------
    _read(
        "list_rooms",
        "Every room with how dirty it is overall (band fresh/aging/due/overdue), its task count "
        "and how many tasks are due. Gives room ids.",
        "/api/rooms",
    ),
    Tool(
        name="create_room",
        description="Add an empty room. To add a room with a ready-made starter task list, use add_rooms_with_starter_tasks.",
        method="POST",
        path="/api/rooms",
        properties={"name": _str("Room name, e.g. \"Kitchen\".", min_length=1, max_length=100)},
        required=("name",),
    ),
    Tool(
        name="update_room",
        description="Rename a room, change its position in the list, or move it into or out of a FlyLady zone.",
        method="PATCH",
        path="/api/rooms/{room_id}",
        properties={
            "room_id": ROOM_ID,
            "name": _str("New name.", min_length=1, max_length=100),
            "sort_order": _int("Position in the room list (0 = first)."),
            "zone_id": _int("Put the room in this zone (from list_zones)."),
            "clear_zone": _bool("True to take the room out of its zone."),
        },
        required=("room_id",),
        idempotent=True,
    ),
    Tool(
        name="delete_room",
        description="Delete a room. Its tasks are kept and become \"no room\" tasks.",
        method="DELETE",
        path="/api/rooms/{room_id}",
        properties={"room_id": ROOM_ID},
        required=("room_id",),
        destructive=True,
        idempotent=True,
    ),
    Tool(
        name="add_rooms_with_starter_tasks",
        description=(
            "The setup wizard: add one or more rooms and auto-generate a sensible starter task list "
            "for each (cadence, time, effort tuned by room type). Only ever adds; safe to run again."
        ),
        method="POST",
        path="/api/onboarding",
        properties={
            "rooms": {
                "type": "array",
                "minItems": 1,
                "description": "Rooms to add.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": _str("Room name.", min_length=1, max_length=100),
                        "type": _str("Room template; anything unknown gets a generic list.", enum=ROOM_TYPES),
                    },
                    "required": ["name", "type"],
                    "additionalProperties": False,
                },
            },
            "has_pets": _bool("True if the household has pets (adds pet-hair tasks)."),
            "has_kids": _bool("True if the household has kids."),
            "enable_zones": _bool("True to also turn on FlyLady zones and map the new rooms into them."),
        },
        required=("rooms",),
    ),
    # ---- Tasks ----------------------------------------------------------
    _read(
        "list_tasks",
        "All tasks, dirtiest first, with each one's decay state: ratio (time since done ÷ cadence) "
        "and band (fresh <0.5, aging, due ≥0.9, overdue ≥1.2, or waiting for a zone task outside "
        "its week). Filter by room, effort, maintenance vs cleaning, or name. Gives task ids.",
        "/api/tasks",
        {
            "room_id": _int("Only this room's tasks (from list_rooms)."),
            "effort": _str("Only quick or only deep tasks.", enum=EFFORT),
            "category": _str("maintenance for the maintenance lane only, cleaning for everything else.", enum=["cleaning", "maintenance"]),
            "include_inactive": _bool("True to include archived (inactive) tasks."),
            "name_contains": _str("Only tasks whose name contains this text (case-insensitive)."),
            "band": _str("Only tasks in this band.", enum=["fresh", "aging", "due", "overdue", "waiting"]),
        },
        query=("room_id", "effort", "category", "include_inactive"),
        shape="filter_tasks",
    ),
    Tool(
        name="create_task",
        description="Add a cleaning or maintenance task. It starts as never done, so it surfaces soon.",
        method="POST",
        path="/api/tasks",
        properties={"name": _str("What to do, e.g. \"Wipe counters\".", min_length=1, max_length=200), **TASK_FIELDS},
        required=("name", "cadence_days", "estimated_minutes"),
    ),
    Tool(
        name="update_task",
        description=(
            "Change a task: name, room, type, cadence, time, effort, assignee, supplies, notes, "
            "preferred day; archive it (is_active=false) or bring it back; or correct when it was "
            "last done (this is a history correction, not a completion — use complete_task for that)."
        ),
        method="PATCH",
        path="/api/tasks/{task_id}",
        properties={
            "task_id": TASK_ID,
            "name": _str("New name.", min_length=1, max_length=200),
            **TASK_FIELDS,
            "clear_room": _bool("True to remove the task from its room."),
            "clear_assignee": _bool("True to unassign it."),
            "clear_preferred_day": _bool("True to remove its preferred day."),
            "is_active": _bool("False archives the task (hidden everywhere, history kept); true restores it."),
            "last_done_at": _str(
                "When it was really last done, ISO 8601 date-time (e.g. 2026-11-10T09:00:00-05:00). Not in the future."
            ),
            "clear_last_done": _bool("True to mark it as never done."),
        },
        required=("task_id",),
        idempotent=True,
    ),
    Tool(
        name="delete_task",
        description="Permanently delete a task and its completion history. To just hide it, use update_task with is_active=false.",
        method="DELETE",
        path="/api/tasks/{task_id}",
        properties={"task_id": TASK_ID},
        required=("task_id",),
        destructive=True,
        idempotent=True,
    ),
    Tool(
        name="complete_task",
        description=(
            "Mark a task done now: resets its decay, logs it for today, ticks it on any running "
            "campaign and may earn badges. A kid's completion notifies the adults. Returns "
            "completion_id for undo_completion."
        ),
        method="POST",
        path="/api/tasks/{task_id}/complete",
        properties={
            "task_id": TASK_ID,
            "source": _str("Where it was done from; leave as direct unless in a session or campaign.", enum=SOURCES),
        },
        required=("task_id",),
    ),
    Tool(
        name="undo_completion",
        description=(
            "Undo one of today's completions (a mis-tap), restoring the task's previous state. Only "
            "today's, and only the task's latest one. completion_id comes from complete_task or get_done_today."
        ),
        method="POST",
        path="/api/completions/{completion_id}/undo",
        properties={"completion_id": _int("The completion's id.")},
        required=("completion_id",),
    ),
    Tool(
        name="claim_task",
        description="Claim an up-for-grabs chore (from get_my_chores) so it's yours and nobody doubles up.",
        method="POST",
        path="/api/tasks/{task_id}/claim",
        properties={"task_id": TASK_ID},
        required=("task_id",),
        idempotent=True,
    ),
    Tool(
        name="snooze_task",
        description=(
            "Snooze a task without marking it done: hides it from suggestions until later today, "
            "tomorrow or in a few days, with a gentle reminder then. \"wake\" un-snoozes it now."
        ),
        method="POST",
        path="/api/tasks/{task_id}/snooze",
        properties={
            "task_id": TASK_ID,
            "option": _str("How long to snooze.", enum=["later_today", "tomorrow", "few_days", "wake"]),
        },
        required=("task_id", "option"),
        idempotent=True,
    ),
    # ---- Cleaning sessions ---------------------------------------------
    Tool(
        name="build_cleaning_session",
        description=(
            "Plan a focus session: the best tasks that fit a time budget, optionally limited to a "
            "room, effort level, zone, guest mode or a campaign. Nothing is changed. Present tasks "
            "one at a time; call complete_task as each is done and finish_cleaning_session at the end."
        ),
        method="POST",
        path="/api/sessions/build",
        properties=SESSION_FIELDS,
        read_only=True,
    ),
    Tool(
        name="finish_cleaning_session",
        description="End a focus session: runs the session badge check and returns any badges newly earned since it started.",
        method="POST",
        path="/api/sessions/complete",
        properties={
            "tasks_done": _int("How many tasks were completed in the session.", 0),
            "started_at": _str("When the session started, ISO 8601 date-time, so mid-session badges are included."),
        },
        required=("tasks_done",),
    ),
    Tool(
        name="start_session_timer",
        description="Start a session timer: Tada sends a push notification to the member's devices when the minutes are up.",
        method="POST",
        path="/api/sessions/timer",
        properties={"minutes": _int("Minutes until the alert.", 5, 240)},
        required=("minutes",),
    ),
    Tool(
        name="extend_session_timer",
        description="Add minutes to a running session timer.",
        method="POST",
        path="/api/sessions/timer/{timer_id}/extend",
        properties={"timer_id": TIMER_ID, "minutes": _int("Minutes to add.", 5, 240)},
        required=("timer_id", "minutes"),
    ),
    Tool(
        name="cancel_session_timer",
        description="Cancel a session timer so its alert never fires.",
        method="DELETE",
        path="/api/sessions/timer/{timer_id}",
        properties={"timer_id": TIMER_ID},
        required=("timer_id",),
        destructive=True,
        idempotent=True,
    ),
    # ---- Supplies -------------------------------------------------------
    _read(
        "list_supplies",
        "The cleaning-supply inventory, out and low first, with each supply's status and how many tasks use it. Gives supply ids.",
        "/api/supplies",
    ),
    Tool(
        name="add_supply",
        description="Add a cleaning supply to the inventory (it starts in stock). Link it to tasks with update_task supply_ids.",
        method="POST",
        path="/api/supplies",
        properties={"name": _str("Supply name, e.g. \"Floor cleaner\".", min_length=1, max_length=100)},
        required=("name",),
    ),
    Tool(
        name="update_supply",
        description=(
            "Rename a supply or set its status: flag it low or out (which also adds it to the "
            "household shopping list in Enchanted Spoon, once per run), or back to in_stock."
        ),
        method="PATCH",
        path="/api/supplies/{supply_id}",
        properties={
            "supply_id": SUPPLY_ID,
            "name": _str("New name.", min_length=1, max_length=100),
            "status": _str("in_stock, low or out.", enum=["in_stock", "low", "out"]),
        },
        required=("supply_id",),
        idempotent=True,
        open_world=True,
    ),
    Tool(
        name="delete_supply",
        description="Delete a supply and unlink it from its tasks (the tasks stay).",
        method="DELETE",
        path="/api/supplies/{supply_id}",
        properties={"supply_id": SUPPLY_ID},
        required=("supply_id",),
        destructive=True,
        idempotent=True,
    ),
    # ---- Household members ---------------------------------------------
    _read(
        "list_members",
        "Everyone in the household (adults and kids) with how many active tasks each has assigned. Gives member ids.",
        "/api/members",
    ),
    Tool(
        name="add_member",
        description="Add a household login: a kid (sees only their chores) or another adult (sees everything). Everyone signs in with their own PIN.",
        method="POST",
        path="/api/members",
        properties={
            "name": _str("Their name.", min_length=1, max_length=100),
            "pin": _str("Their sign-in PIN, 4–12 digits, unique in the household.", min_length=4, max_length=12),
            "role": _str("kid or owner (an adult).", enum=["kid", "owner"]),
        },
        required=("name", "pin"),
    ),
    Tool(
        name="update_member",
        description="Rename a household member or change their PIN.",
        method="PATCH",
        path="/api/members/{member_id}",
        properties={
            "member_id": MEMBER_ID,
            "name": _str("New name.", min_length=1, max_length=100),
            "pin": _str("New PIN, 4–12 digits.", min_length=4, max_length=12),
        },
        required=("member_id",),
        idempotent=True,
    ),
    Tool(
        name="remove_member",
        description="Remove a household member's login and their completion history; their tasks stay, unassigned. The last adult can't be removed.",
        method="DELETE",
        path="/api/members/{member_id}",
        properties={"member_id": MEMBER_ID},
        required=("member_id",),
        destructive=True,
        idempotent=True,
    ),
    # ---- Settings & reminders ------------------------------------------
    _read(
        "get_settings",
        "Tada's settings: focus count, default session minutes, morning nudge time, time zone, vacation mode, zones and campaigns on/off.",
        "/api/settings",
    ),
    Tool(
        name="update_settings",
        description=(
            "Change settings. Only send what changes. Morning reminder: daily_nudge_time \"HH:MM\" "
            "(24h) or \"\" to turn it off. Vacation mode: vacation_until = last day away "
            "(YYYY-MM-DD), or \"\" for \"I'm back\"."
        ),
        method="PUT",
        path="/api/settings",
        properties={
            "daily_focus_count": _int("How many tasks the home screen suggests.", 1, 3),
            "default_session_minutes": _int("Default session length in minutes.", 5, 240),
            "daily_nudge_time": _str("Morning nudge time HH:MM (24-hour), or \"\" to turn it off."),
            "timezone": _str("IANA time zone, e.g. America/New_York."),
            "zones_enabled": _bool("Turn the FlyLady zones overlay on or off."),
            "campaigns_enabled": _bool("Turn seasonal campaigns on or off."),
            "vacation_until": _str("Last day away (YYYY-MM-DD) to pause nudges, or \"\" when back."),
            "zone_lane_enabled": _bool("Zone missions keep to their week (the zone scheduling lane)."),
            "zone_3_extra_room_id": _str("Room id (as text) rotating into Zone 3, or \"\" for none."),
        },
        idempotent=True,
    ),
    # ---- Zones ----------------------------------------------------------
    _read(
        "list_zones",
        "The FlyLady zones, their rooms, this week's number and which zone is current. Empty if zones were never set up.",
        "/api/zones",
    ),
    Tool(
        name="set_up_zones",
        description="Create FlyLady's five default zones and map existing rooms into them by name. Safe to repeat. Turn the overlay on with update_settings zones_enabled.",
        method="POST",
        path="/api/zones/setup",
        idempotent=True,
    ),
    Tool(
        name="rename_zone",
        description="Rename a zone. Move rooms between zones with update_room.",
        method="PATCH",
        path="/api/zones/{zone_id}",
        properties={"zone_id": ZONE_ID, "name": _str("New name.", min_length=1, max_length=100)},
        required=("zone_id", "name"),
        idempotent=True,
    ),
    # ---- Campaigns ------------------------------------------------------
    _read(
        "list_campaigns",
        "Seasonal cleaning campaigns (e.g. Spring Cleaning) with dates, whether running, and progress. Gives campaign ids.",
        "/api/campaigns",
    ),
    _read(
        "get_campaign",
        "One campaign with its checklist of tasks and which are done.",
        "/api/campaigns/{campaign_id}",
        {"campaign_id": CAMPAIGN_ID},
        required=("campaign_id",),
    ),
    Tool(
        name="create_campaign",
        description="Create a seasonal campaign over existing tasks. It starts inactive; activate it with update_campaign active=true.",
        method="POST",
        path="/api/campaigns",
        properties={
            "name": _str("Campaign name.", min_length=1, max_length=120),
            "season": _str("Optional season label, e.g. spring.", max_length=50),
            "start_date": _date("First day"),
            "end_date": _date("Last day"),
            "task_ids": _ids("Tasks on its checklist (ids from list_tasks)."),
        },
        required=("name", "start_date", "end_date"),
    ),
    Tool(
        name="update_campaign",
        description="Edit a campaign: name, season, dates, activate/pause it, or replace its task checklist (ticked tasks that stay keep their tick).",
        method="PATCH",
        path="/api/campaigns/{campaign_id}",
        properties={
            "campaign_id": CAMPAIGN_ID,
            "name": _str("New name.", min_length=1, max_length=120),
            "season": _str("Season label, or \"\" to clear.", max_length=50),
            "start_date": _date("First day"),
            "end_date": _date("Last day"),
            "active": _bool("True to activate (shows on the home screen while in its dates), false to pause."),
            "task_ids": _ids("The complete new checklist (ids from list_tasks)."),
        },
        required=("campaign_id",),
        idempotent=True,
    ),
    Tool(
        name="delete_campaign",
        description="Delete a campaign and its checklist (the tasks themselves stay).",
        method="DELETE",
        path="/api/campaigns/{campaign_id}",
        properties={"campaign_id": CAMPAIGN_ID},
        required=("campaign_id",),
        destructive=True,
        idempotent=True,
    ),
    # ---- Lists (packing, shopping, to-do) ------------------------------
    _read(
        "list_list_templates",
        "Starter templates for lists (packing lists, gift and school-supply shopping, to-dos). Pass a template's id to create_list.",
        "/api/lists/templates",
    ),
    _read(
        "list_lists",
        "Every packing/shopping/to-do list (active and archived) with progress and price totals. Gives list ids.",
        "/api/lists",
    ),
    _read(
        "get_list",
        "One list in full: its sections and items, checked or not, with prices.",
        "/api/lists/{list_id}",
        {"list_id": LIST_ID},
        required=("list_id",),
    ),
    Tool(
        name="create_list",
        description="Start a new list by copying a template or an archived list (source_list_id). For a blank list, copy the 'Custom' template.",
        method="POST",
        path="/api/lists",
        properties={
            "source_list_id": _int("Template or archived list to copy (from list_list_templates or list_lists)."),
            "name": _str("Name for the new list; defaults to the source's.", min_length=1, max_length=120),
            "event_date": _date("Trip or event date"),
            "destination": _str("Where you're going (packing lists).", max_length=120),
            "duration": _str("How long, free text, e.g. \"5 days\".", max_length=60),
        },
        required=("source_list_id",),
    ),
    Tool(
        name="update_list",
        description="Edit a list: rename, set or clear its date, destination or duration, archive or restore it, or turn its countdown reminder on/off.",
        method="PATCH",
        path="/api/lists/{list_id}",
        properties={
            "list_id": LIST_ID,
            "name": _str("New name.", min_length=1, max_length=120),
            "event_date": _date("Event date"),
            "clear_event_date": _bool("True to remove the date."),
            "destination": _str("Destination.", max_length=120),
            "clear_destination": _bool("True to remove the destination."),
            "duration": _str("Duration, free text.", max_length=60),
            "clear_duration": _bool("True to remove the duration."),
            "status": _str("active or archived.", enum=["active", "archived"]),
            "reminder_enabled": _bool("Countdown push reminder before the event date (needs a date)."),
            "reminder_days_before": _int("Days before the date to remind.", 0, 30),
        },
        required=("list_id",),
        idempotent=True,
    ),
    Tool(
        name="delete_list",
        description="Permanently delete a list made by mistake. Finished lists are better archived (update_list status=archived).",
        method="DELETE",
        path="/api/lists/{list_id}",
        properties={"list_id": LIST_ID},
        required=("list_id",),
        destructive=True,
        idempotent=True,
    ),
    Tool(
        name="add_list_section",
        description="Add a section (a group of items, e.g. \"Toiletries\") to a list.",
        method="POST",
        path="/api/lists/{list_id}/sections",
        properties={"list_id": LIST_ID, "name": _str("Section name.", min_length=1, max_length=120)},
        required=("list_id", "name"),
    ),
    Tool(
        name="update_list_section",
        description="Rename a list section or move it to a new position.",
        method="PATCH",
        path="/api/lists/sections/{section_id}",
        properties={
            "section_id": SECTION_ID,
            "name": _str("New name.", min_length=1, max_length=120),
            "sort_order": _int("New position (0 = first).", 0),
        },
        required=("section_id",),
        idempotent=True,
    ),
    Tool(
        name="delete_list_section",
        description="Delete a list section and all its items.",
        method="DELETE",
        path="/api/lists/sections/{section_id}",
        properties={"section_id": SECTION_ID},
        required=("section_id",),
        destructive=True,
        idempotent=True,
    ),
    Tool(
        name="add_list_item",
        description="Add an item to a list section.",
        method="POST",
        path="/api/lists/sections/{section_id}/items",
        properties={
            "section_id": SECTION_ID,
            "name": _str("Item name.", min_length=1, max_length=200),
            "quantity": _str("Quantity, free text, e.g. \"2\" or \"1 pack\".", max_length=50),
            "notes": _str("Notes."),
            "price": _money("Price."),
        },
        required=("section_id", "name"),
    ),
    Tool(
        name="update_list_item",
        description="Edit a list item: check or uncheck it (packed), rename it, change quantity, notes or price, or move it.",
        method="PATCH",
        path="/api/lists/items/{item_id}",
        properties={
            "item_id": ITEM_ID,
            "packed": _bool("True to check it off, false to uncheck."),
            "name": _str("New name.", min_length=1, max_length=200),
            "quantity": _str("Quantity.", max_length=50),
            "clear_quantity": _bool("True to remove the quantity."),
            "notes": _str("Notes."),
            "clear_notes": _bool("True to remove the notes."),
            "price": _money("Price."),
            "clear_price": _bool("True to remove the price."),
            "sort_order": _int("New position in its section (0 = first).", 0),
        },
        required=("item_id",),
        idempotent=True,
    ),
    Tool(
        name="delete_list_item",
        description="Delete an item from a list.",
        method="DELETE",
        path="/api/lists/items/{item_id}",
        properties={"item_id": ITEM_ID},
        required=("item_id",),
        destructive=True,
        idempotent=True,
    ),
    # ---- Feedback -------------------------------------------------------
    Tool(
        name="send_feedback",
        description="Send Mitchell feedback about Tada (a bug or an idea); it files an issue on Tada's GitHub repo.",
        method="POST",
        path="/api/feedback",
        properties={
            "category": _str("What kind of feedback.", enum=["Something's broken", "Idea"]),
            "message": _str("The feedback, at least 10 characters.", min_length=10, max_length=5000),
        },
        required=("category", "message"),
        open_world=True,
    ),
]

TOOLS_BY_NAME: dict[str, Tool] = {tool.name: tool for tool in TOOLS}

#: User-facing routes deliberately without a tool, and why.
LEFT_OUT: dict[tuple[str, str], str] = {
    ("POST", "/api/auth/login"): "sign-in is the consent page's job",
    ("POST", "/api/auth/logout"): "sign-out only makes sense in the app",
    ("POST", "/api/push/subscribe"): "registers this browser for notifications; UI only",
}

#: Route prefixes that aren't user actions: device/app integrations with
#: their own tokens, and the connector itself.
EXCLUDED_PREFIXES = ("/api/hearth", "/api/orbit", "/api/oauth", "/api/mcp")
