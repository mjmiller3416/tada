import { TaskRow } from "tada-frontend";

/** Realistic Task objects (SPEC §3/§4 shape) for planning-list rows. */
const task = (over: Record<string, unknown>) => ({
  id: 1,
  name: "Wipe the counters",
  room_id: 1,
  room_name: "Kitchen",
  category: "cleaning",
  cadence_days: 7,
  estimated_minutes: 15,
  effort: "quick",
  guest_facing: false,
  last_done_at: null,
  snoozed_until: null,
  is_snoozed: false,
  is_active: true,
  assignee_id: null,
  assignee_name: null,
  claimable: false,
  supplies: [],
  notes: null,
  ratio: 0.4,
  band: "aging",
  ...over,
});

const list: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 8,
  width: 360,
};

/** A planning list across the four dirtiness bands. */
export const PlanningList = () => (
  <div style={list}>
    <TaskRow task={task({ id: 1, name: "Wipe the counters", band: "fresh", ratio: 0.1 })} />
    <TaskRow
      task={task({
        id: 2,
        name: "Vacuum the rug",
        room_name: "Living room",
        room_id: 5,
        band: "aging",
        cadence_days: 14,
        estimated_minutes: 20,
      })}
    />
    <TaskRow
      task={task({
        id: 3,
        name: "Scrub the shower",
        room_name: "Bathroom",
        room_id: 2,
        band: "due",
        cadence_days: 30,
        estimated_minutes: 25,
        effort: "deep",
      })}
    />
    <TaskRow
      task={task({
        id: 4,
        name: "Clean the oven",
        band: "overdue",
        cadence_days: 91,
        estimated_minutes: 45,
        effort: "deep",
        ratio: 1.4,
      })}
    />
  </div>
);

/** Maintenance rows check off straight from the list (the ✓ button). */
export const WithCheckOff = () => (
  <div style={list}>
    <TaskRow
      task={task({
        id: 5,
        name: "Change the furnace filter",
        room_name: null,
        room_id: null,
        category: "maintenance",
        cadence_days: 91,
        band: "due",
      })}
      onDone={() => {}}
    />
    <TaskRow
      task={task({
        id: 6,
        name: "Test smoke detectors",
        room_name: null,
        room_id: null,
        category: "maintenance",
        cadence_days: 365,
        estimated_minutes: 10,
        band: "fresh",
      })}
      onDone={() => {}}
    />
  </div>
);

/** Assigned, up-for-grabs, resting, and archived states. */
export const States = () => (
  <div style={list}>
    <TaskRow
      task={task({ id: 7, name: "Feed the cat", assignee_id: 2, assignee_name: "Maya", band: "fresh", cadence_days: 1, estimated_minutes: 5 })}
    />
    <TaskRow
      task={task({ id: 8, name: "Water the plants", claimable: true, band: "due", cadence_days: 3, estimated_minutes: 10 })}
    />
    <TaskRow
      task={task({
        id: 9,
        name: "Mop the floors",
        is_snoozed: true,
        snoozed_until: "2026-07-24T09:00:00",
        band: "aging",
        estimated_minutes: 30,
      })}
    />
    <TaskRow task={task({ id: 10, name: "Polish the silver", is_active: false, band: "fresh" })} />
  </div>
);

/** Inside a room's own page the room chip is hidden. */
export const HideRoom = () => (
  <div style={list}>
    <TaskRow task={task({ id: 11, name: "Wipe the counters", band: "due" })} hideRoom />
    <TaskRow
      task={task({ id: 12, name: "Clean out the fridge", band: "overdue", cadence_days: 30, effort: "deep" })}
      hideRoom
    />
  </div>
);
