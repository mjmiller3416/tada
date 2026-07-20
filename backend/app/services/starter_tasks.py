"""Starter task generation for the onboarding wizard (SPEC §6).

Given the rooms she picks (each tagged with a room *type*) and a little
household context (pets, kids), auto-generate a sensible working schedule
— default cadences, time estimates, and effort per room — that she then
edits rather than builds from scratch.

Cadence values use the SPEC §3 tier presets: daily=1, weekly=7,
monthly=30, seasonal=91, annual=365 (plus in-between customs where a
default genuinely sits between tiers).
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.room import Room
from app.models.task import Task


@dataclass(frozen=True)
class StarterTask:
    name: str
    cadence_days: int
    estimated_minutes: int
    effort: str  # "quick" | "deep"
    guest_facing: bool = False


#: Templates per room type. Types line up with the wizard's room picker;
#: unknown/custom types fall back to GENERIC.
TEMPLATES: dict[str, list[StarterTask]] = {
    "kitchen": [
        StarterTask("Wipe down the counters", 1, 5, "quick", guest_facing=True),
        StarterTask("Do the dishes / load the dishwasher", 1, 15, "quick"),
        StarterTask("Sweep the floor", 3, 10, "quick"),
        StarterTask("Wipe the stovetop", 7, 10, "quick"),
        StarterTask("Take out the trash & recycling", 3, 5, "quick"),
        StarterTask("Clean the microwave", 14, 10, "quick"),
        StarterTask("Mop the floor", 14, 20, "deep"),
        StarterTask("Wipe cabinet fronts & handles", 30, 15, "quick"),
        StarterTask("Clean out the fridge", 30, 25, "deep"),
        StarterTask("Deep-clean the oven", 91, 45, "deep"),
    ],
    "bathroom": [
        StarterTask("Wipe the sink & counter", 3, 5, "quick", guest_facing=True),
        StarterTask("Clean the toilet", 7, 10, "quick", guest_facing=True),
        StarterTask("Clean the mirror", 7, 5, "quick", guest_facing=True),
        StarterTask("Scrub the shower / tub", 14, 25, "deep"),
        StarterTask("Swap the towels", 7, 5, "quick"),
        StarterTask("Mop the floor", 14, 10, "quick"),
        StarterTask("Wash the bath mats", 30, 10, "quick"),
    ],
    "bedroom": [
        StarterTask("Make the bed", 1, 3, "quick"),
        StarterTask("Quick tidy — clothes & surfaces", 3, 10, "quick"),
        StarterTask("Change the sheets", 7, 15, "quick"),
        StarterTask("Dust the surfaces", 14, 10, "quick"),
        StarterTask("Vacuum the floor", 7, 10, "quick"),
        StarterTask("Declutter one drawer or shelf", 30, 15, "deep"),
    ],
    "living_room": [
        StarterTask("Reset pillows & fold blankets", 1, 5, "quick", guest_facing=True),
        StarterTask("Quick tidy — put things back home", 1, 10, "quick", guest_facing=True),
        StarterTask("Dust the surfaces & shelves", 7, 15, "quick", guest_facing=True),
        StarterTask("Vacuum the floor & rug", 7, 15, "quick", guest_facing=True),
        StarterTask("Wipe the TV & electronics", 14, 5, "quick"),
        StarterTask("Vacuum under the cushions", 30, 10, "deep"),
        StarterTask("Wash the windows", 91, 30, "deep"),
    ],
    "dining_room": [
        StarterTask("Wipe the table", 1, 5, "quick", guest_facing=True),
        StarterTask("Sweep or vacuum the floor", 7, 10, "quick", guest_facing=True),
        StarterTask("Dust the surfaces", 14, 10, "quick", guest_facing=True),
        StarterTask("Polish the table & chairs", 91, 20, "deep"),
    ],
    "office": [
        StarterTask("Clear the desk", 3, 5, "quick"),
        StarterTask("Dust the desk & shelves", 14, 10, "quick"),
        StarterTask("Vacuum the floor", 14, 10, "quick"),
        StarterTask("Sort the paper pile", 30, 20, "deep"),
    ],
    "laundry": [
        StarterTask("Run & fold a load of laundry", 2, 20, "quick"),
        StarterTask("Wipe the machines", 30, 5, "quick"),
        StarterTask("Clean the lint trap area", 30, 10, "quick"),
        StarterTask("Deep-clean the washer (empty hot run)", 91, 10, "deep"),
    ],
    "entryway": [
        StarterTask("Tidy shoes & coats", 2, 5, "quick", guest_facing=True),
        StarterTask("Sweep or vacuum the floor", 7, 5, "quick", guest_facing=True),
        StarterTask("Shake out the doormat", 14, 5, "quick"),
        StarterTask("Wipe the front door & handle", 30, 5, "quick", guest_facing=True),
    ],
    "hallway": [
        StarterTask("Quick tidy", 7, 5, "quick", guest_facing=True),
        StarterTask("Vacuum the floor", 7, 10, "quick", guest_facing=True),
        StarterTask("Dust ledges & frames", 30, 10, "quick"),
    ],
    "playroom": [
        StarterTask("Toy reset — everything back in its bin", 1, 10, "quick"),
        StarterTask("Vacuum the floor", 7, 10, "quick"),
        StarterTask("Wipe surfaces & toy shelves", 14, 10, "quick"),
        StarterTask("Declutter outgrown toys", 91, 30, "deep"),
    ],
    "garage": [
        StarterTask("Quick sweep", 30, 15, "quick"),
        StarterTask("Tidy the workbench / shelves", 30, 20, "deep"),
        StarterTask("Declutter one corner", 91, 30, "deep"),
    ],
    "basement": [
        StarterTask("Quick tidy", 14, 10, "quick"),
        StarterTask("Vacuum or sweep", 30, 15, "quick"),
        StarterTask("Declutter one shelf or bin", 91, 30, "deep"),
    ],
}

#: Fallback for custom room types.
GENERIC: list[StarterTask] = [
    StarterTask("Quick tidy", 3, 10, "quick"),
    StarterTask("Dust the surfaces", 14, 10, "quick"),
    StarterTask("Vacuum or sweep the floor", 7, 10, "quick"),
    StarterTask("Declutter one spot", 30, 15, "deep"),
]

#: Household-context tweaks. With pets, floors need love more often; with
#: kids, tidying resets more often. Applied by simple name matching on
#: the generated defaults — she can retune anything afterwards.
PET_FLOOR_KEYWORDS = ("vacuum", "sweep", "mop")
KID_TIDY_KEYWORDS = ("tidy", "reset", "declutter one spot")


def _adjusted_cadence(task: StarterTask, has_pets: bool, has_kids: bool) -> int:
    name = task.name.lower()
    cadence = task.cadence_days
    if has_pets and any(word in name for word in PET_FLOOR_KEYWORDS):
        cadence = max(1, cadence // 2)
    if has_kids and any(word in name for word in KID_TIDY_KEYWORDS):
        cadence = max(1, cadence // 2)
    return cadence


def generate_for_room(
    db: Session, room: Room, room_type: str, *, has_pets: bool, has_kids: bool
) -> list[Task]:
    """Create (but don't commit) the starter Task rows for one room."""
    template = TEMPLATES.get(room_type, GENERIC)
    tasks: list[Task] = []
    for item in template:
        task = Task(
            name=item.name,
            room_id=room.id,
            category="cleaning",
            cadence_days=_adjusted_cadence(item, has_pets, has_kids),
            estimated_minutes=item.estimated_minutes,
            effort=item.effort,
            guest_facing=item.guest_facing,
            is_active=True,
        )
        db.add(task)
        tasks.append(task)
    return tasks
