"use client";

import { useEffect, useState } from "react";
import {
  createTask,
  deleteTask,
  getMembers,
  getSupplies,
  updateTask,
  type Effort,
  type Member,
  type Room,
  type Supply,
  type Task,
  type TaskType,
} from "@/lib/api";
import { CADENCE_PRESETS, TASK_TYPE_LABEL } from "@/lib/decay";
import { fromLocalDateValue, toLocalDateValue } from "@/lib/dates";
import { Button, Card, Chip } from "@/components/ui";
import styles from "./TaskForm.module.css";

type TaskFormProps = {
  /** Existing task to edit, or null to create a new one. */
  task: Task | null;
  rooms: Room[];
  /** Preselected room for new tasks (e.g. adding from a room page). */
  defaultRoomId?: number | null;
  /** Preselected type for new tasks (e.g. adding from the maintenance view). */
  defaultTaskType?: TaskType;
  /** Called with true when something changed and lists should refetch. */
  onClose: (changed: boolean) => void;
};

const CUSTOM = "custom";

const TASK_TYPES = Object.keys(TASK_TYPE_LABEL) as TaskType[];

/** What each lane means, in her words — a preference guide, never jargon
 * (the Phase 11 reclassification review leans on these). */
const TASK_TYPE_HINT: Record<TaskType, string> = {
  routine: "Everyday upkeep — comes up whenever it needs doing.",
  weekly_blessing: "The weekly once-over — vacuum, mop, sheets, towels.",
  zone: "A small detail mission — only comes up during its room’s zone week.",
  maintenance: "Long-haul home care — lives in its own list, out of the daily flow.",
  project: "A someday project — only when you choose it. Never nagged.",
};

// Python weekday() convention, matching the backend: Monday = 0 … Sunday = 6.
const DAY_CHIPS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const DAY_NAMES = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];

function presetFor(days: number): string {
  const preset = CADENCE_PRESETS.find((p) => p.days === days);
  return preset ? String(preset.days) : CUSTOM;
}

/**
 * Add/edit a task (SPEC §6 "Cadence tiers + custom"): tier preset chips
 * with a custom day count, time estimate, effort, room, and notes — plus
 * the Phase 2 fields: category (cleaning vs maintenance), whose job it
 * is (assign / leave up for grabs), and the supplies it uses.
 * Rendered as a full-screen overlay — heavy editing is a Chromebook
 * activity, but everything still works one-handed on the phone.
 */
export default function TaskForm({
  task,
  rooms,
  defaultRoomId = null,
  defaultTaskType = "routine",
  onClose,
}: TaskFormProps) {
  const [name, setName] = useState(task?.name ?? "");
  const [roomId, setRoomId] = useState<number | null>(
    task ? task.room_id : defaultRoomId,
  );
  // The five-type editor (Phase 11): which clock schedules this task —
  // SPEC §4's scheduling lanes, in plain language.
  const [taskType, setTaskType] = useState<TaskType>(
    task ? task.task_type : defaultTaskType,
  );
  const [cadenceChoice, setCadenceChoice] = useState<string>(
    presetFor(task?.cadence_days ?? 7),
  );
  const [customDays, setCustomDays] = useState<string>(
    String(task?.cadence_days ?? 7),
  );
  const [minutes, setMinutes] = useState<string>(
    String(task?.estimated_minutes ?? 10),
  );
  const [effort, setEffort] = useState<Effort>(task?.effort ?? "quick");
  // Preferred day (Phase 8): a preference, never a deadline — the task
  // just gets a friendly boost that day (and the day after).
  const [preferredDay, setPreferredDay] = useState<number | null>(
    task?.preferred_day ?? null,
  );
  const [assigneeId, setAssigneeId] = useState<number | null>(
    task?.assignee_id ?? null,
  );
  const [claimable, setClaimable] = useState(task?.claimable ?? false);
  const [supplyIds, setSupplyIds] = useState<number[]>(
    task ? task.supplies.map((s) => s.id) : [],
  );
  const [notes, setNotes] = useState(task?.notes ?? "");
  const [isActive, setIsActive] = useState(task?.is_active ?? true);
  // "When was this last done?" (Phase 4.6) — kept as the date-input
  // string so we only send a change when she actually edits it.
  const initialLastDone =
    task?.last_done_at != null ? toLocalDateValue(task.last_done_at) : "";
  const [lastDone, setLastDone] = useState(initialLastDone);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [members, setMembers] = useState<Member[]>([]);
  const [supplies, setSupplies] = useState<Supply[]>([]);

  useEffect(() => {
    getMembers()
      .then(setMembers)
      .catch(() => {});
    getSupplies()
      .then(setSupplies)
      .catch(() => {});
  }, []);

  const cadenceDays =
    cadenceChoice === CUSTOM ? parseInt(customDays, 10) : parseInt(cadenceChoice, 10);
  const estimatedMinutes = parseInt(minutes, 10);
  const valid =
    name.trim().length > 0 &&
    Number.isFinite(cadenceDays) &&
    cadenceDays >= 1 &&
    Number.isFinite(estimatedMinutes) &&
    estimatedMinutes >= 1;

  function toggleSupply(id: number) {
    setSupplyIds((current) =>
      current.includes(id) ? current.filter((s) => s !== id) : [...current, id],
    );
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!valid || saving) return;
    setSaving(true);
    setError(null);
    try {
      if (task) {
        await updateTask(task.id, {
          name: name.trim(),
          ...(roomId != null ? { room_id: roomId } : { clear_room: true }),
          task_type: taskType,
          cadence_days: cadenceDays,
          estimated_minutes: estimatedMinutes,
          effort,
          ...(preferredDay != null
            ? { preferred_day: preferredDay }
            : { clear_preferred_day: true }),
          ...(assigneeId != null
            ? { assignee_id: assigneeId }
            : { clear_assignee: true }),
          claimable,
          supply_ids: supplyIds,
          notes: notes.trim() || null,
          is_active: isActive,
          // Only send when she changed it — an untouched date must not
          // quietly rewrite the precise last-done timestamp.
          ...(lastDone !== initialLastDone
            ? lastDone === ""
              ? { clear_last_done: true }
              : { last_done_at: fromLocalDateValue(lastDone) }
            : {}),
        });
      } else {
        await createTask({
          name: name.trim(),
          room_id: roomId,
          task_type: taskType,
          cadence_days: cadenceDays,
          estimated_minutes: estimatedMinutes,
          effort,
          preferred_day: preferredDay,
          assignee_id: assigneeId,
          claimable,
          supply_ids: supplyIds,
          notes: notes.trim() || null,
        });
      }
      onClose(true);
    } catch {
      setError("That didn’t save — give it another try.");
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!task || saving) return;
    if (!window.confirm(`Remove “${task.name}” and its history for good?`)) return;
    setSaving(true);
    try {
      await deleteTask(task.id);
      onClose(true);
    } catch {
      setError("That didn’t work — give it another try.");
      setSaving(false);
    }
  }

  const kids = members.filter((m) => m.role === "kid");

  return (
    <div className={styles.overlay} role="dialog" aria-modal="true">
      <Card padding="lg" className={styles.sheet}>
        <h2 className={styles.title}>{task ? "Edit task" : "New task"}</h2>

        <form onSubmit={handleSave} className={styles.form}>
          <label className={styles.field}>
            <span className={styles.label}>What’s the task?</span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Wipe down the counters"
              className={styles.input}
              autoFocus={!task}
            />
          </label>

          <label className={styles.field}>
            <span className={styles.label}>Room</span>
            <select
              value={roomId ?? ""}
              onChange={(e) =>
                setRoomId(e.target.value === "" ? null : Number(e.target.value))
              }
              className={styles.input}
            >
              <option value="">No room</option>
              {rooms.map((room) => (
                <option key={room.id} value={room.id}>
                  {room.name}
                </option>
              ))}
            </select>
          </label>

          <div className={styles.field}>
            <span className={styles.label}>What kind of task?</span>
            <div className={styles.chips}>
              {TASK_TYPES.map((type) => (
                <Chip
                  key={type}
                  tone={taskType === type ? "coral" : "neutral"}
                  onClick={() => setTaskType(type)}
                >
                  {TASK_TYPE_LABEL[type]}
                </Chip>
              ))}
            </div>
            <span className={styles.hint}>{TASK_TYPE_HINT[taskType]}</span>
          </div>

          <div className={styles.field}>
            <span className={styles.label}>How often does it need doing?</span>
            <div className={styles.chips}>
              {CADENCE_PRESETS.map((preset) => (
                <Chip
                  key={preset.days}
                  tone={cadenceChoice === String(preset.days) ? "coral" : "neutral"}
                  onClick={() => setCadenceChoice(String(preset.days))}
                >
                  {preset.label}
                </Chip>
              ))}
              <Chip
                tone={cadenceChoice === CUSTOM ? "coral" : "neutral"}
                onClick={() => setCadenceChoice(CUSTOM)}
              >
                Custom
              </Chip>
            </div>
            {cadenceChoice === CUSTOM && (
              <label className={styles.customDays}>
                Every
                <input
                  type="number"
                  min={1}
                  max={730}
                  value={customDays}
                  onChange={(e) => setCustomDays(e.target.value)}
                  className={`${styles.input} ${styles.numberInput}`}
                />
                days
              </label>
            )}
          </div>

          <div className={styles.field}>
            <span className={styles.label}>Usually a certain day? (optional)</span>
            <div className={styles.chips}>
              <Chip
                tone={preferredDay === null ? "coral" : "neutral"}
                onClick={() => setPreferredDay(null)}
              >
                No set day
              </Chip>
              {DAY_CHIPS.map((label, day) => (
                <Chip
                  key={label}
                  tone={preferredDay === day ? "coral" : "neutral"}
                  onClick={() => setPreferredDay(day)}
                >
                  {label}
                </Chip>
              ))}
            </div>
            <span className={styles.hint}>
              {preferredDay !== null
                ? `Usually a ${DAY_NAMES[preferredDay]} job — it’ll get a friendly nudge up the list that day (and the day after). Never a deadline.`
                : "Just a preference, if this one has a rhythm — it’ll get a friendly nudge that day, never a due date."}
            </span>
          </div>

          {task && (
            <label className={styles.field}>
              <span className={styles.label}>When was it last done?</span>
              <input
                type="date"
                value={lastDone}
                max={toLocalDateValue()}
                onChange={(e) => setLastDone(e.target.value)}
                className={styles.input}
              />
              <span className={styles.hint}>
                If real life got ahead of Tada, set the date straight and it
                won’t come up early. Leave it blank if it hasn’t been done yet.
              </span>
            </label>
          )}

          <div className={styles.twoUp}>
            <label className={styles.field}>
              <span className={styles.label}>About how long?</span>
              <label className={styles.customDays}>
                <input
                  type="number"
                  min={1}
                  max={480}
                  value={minutes}
                  onChange={(e) => setMinutes(e.target.value)}
                  className={`${styles.input} ${styles.numberInput}`}
                />
                minutes
              </label>
            </label>

            <div className={styles.field}>
              <span className={styles.label}>Effort</span>
              <div className={styles.chips}>
                <Chip
                  tone={effort === "quick" ? "coral" : "neutral"}
                  onClick={() => setEffort("quick")}
                >
                  Quick win
                </Chip>
                <Chip
                  tone={effort === "deep" ? "coral" : "neutral"}
                  onClick={() => setEffort("deep")}
                >
                  Deep clean
                </Chip>
              </div>
            </div>
          </div>

          {members.length > 1 && (
            <div className={styles.field}>
              <span className={styles.label}>Whose job is it?</span>
              <select
                value={assigneeId ?? ""}
                onChange={(e) =>
                  setAssigneeId(
                    e.target.value === "" ? null : Number(e.target.value),
                  )
                }
                className={styles.input}
              >
                <option value="">Nobody in particular</option>
                {members.map((member) => (
                  <option key={member.id} value={member.id}>
                    {member.name}
                  </option>
                ))}
              </select>
              {assigneeId == null && kids.length > 0 && (
                <label className={styles.toggleRow}>
                  <input
                    type="checkbox"
                    checked={claimable}
                    onChange={(e) => setClaimable(e.target.checked)}
                  />
                  Let the kids claim this one
                </label>
              )}
            </div>
          )}

          {supplies.length > 0 && (
            <div className={styles.field}>
              <span className={styles.label}>Supplies it uses</span>
              <div className={styles.chips}>
                {supplies.map((supply) => (
                  <Chip
                    key={supply.id}
                    tone={supplyIds.includes(supply.id) ? "teal" : "neutral"}
                    onClick={() => toggleSupply(supply.id)}
                  >
                    {supply.name}
                  </Chip>
                ))}
              </div>
            </div>
          )}

          <label className={styles.field}>
            <span className={styles.label}>Notes (optional)</span>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              className={styles.input}
            />
          </label>

          {task && (
            <label className={styles.toggleRow}>
              <input
                type="checkbox"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
              />
              Active (untick to archive — it keeps its history, just rests)
            </label>
          )}

          {error && <p className={styles.error}>{error}</p>}

          <div className={styles.actions}>
            <Button type="submit" variant="primary" size="lg" fullWidth disabled={!valid || saving}>
              {saving ? "Saving…" : task ? "Save changes" : "Add task"}
            </Button>
            <Button type="button" variant="ghost" fullWidth onClick={() => onClose(false)}>
              Cancel
            </Button>
            {task && (
              <Button
                type="button"
                variant="ghost"
                fullWidth
                onClick={handleDelete}
                className={styles.deleteButton}
              >
                Delete task
              </Button>
            )}
          </div>
        </form>
      </Card>
    </div>
  );
}
