"use client";

import { updateTask, type Task, type TaskType } from "@/lib/api";
import {
  EFFORT_LABEL,
  TASK_TYPE_LABEL,
  cadenceLabel,
  roomTone,
  snoozedLabel,
  waitingLabel,
} from "@/lib/decay";
import { Chip } from "@/components/ui";
import DirtinessDot from "./DirtinessDot";
import styles from "./TaskRow.module.css";

const TASK_TYPES = Object.keys(TASK_TYPE_LABEL) as TaskType[];

type TaskRowProps = {
  task: Task;
  /** Hide the room chip (e.g. inside that room's own page). */
  hideRoom?: boolean;
  /**
   * When provided, shows a small ✓ check-off button. Used for the
   * maintenance section, where tasks are done straight from the list —
   * they never appear in focus sessions.
   */
  onDone?: () => void;
  onClick?: () => void;
  /**
   * When provided, the type chip becomes an inline editor (Phase 11's
   * reclassification review): pick a lane right from the row, no form
   * needed. Called after a successful save so the list can refetch.
   */
  onTypeChanged?: () => void;
};

/**
 * One task in a planning list (room detail / global view). Planning
 * surfaces show everything — including fresh, resting, and (Phase 11)
 * out-of-window zone missions, which show a quiet muted "waits for
 * Kitchen week" instead of a band color (SPEC §4: never debt).
 */
export default function TaskRow({
  task,
  hideRoom = false,
  onDone,
  onClick,
  onTypeChanged,
}: TaskRowProps) {
  async function handleTypeChange(taskType: TaskType) {
    try {
      await updateTask(task.id, { task_type: taskType });
    } finally {
      onTypeChanged?.();
    }
  }

  return (
    <div className={styles.rowWrap}>
      {/* A div, not a button: the inline type select lives inside it and
          interactive elements can't nest. */}
      <div
        role="button"
        tabIndex={0}
        className={styles.row}
        onClick={onClick}
        onKeyDown={(e) => {
          if (e.key === "Enter" && e.target === e.currentTarget) onClick?.();
        }}
      >
        <DirtinessDot band={task.band} />
        <span className={styles.body}>
          <span className={styles.name}>
            {task.name}
            {!task.is_active && <span className={styles.archived}> · archived</span>}
          </span>
          <span className={styles.meta}>
            {cadenceLabel(task.cadence_days)} · about {task.estimated_minutes} min ·{" "}
            {EFFORT_LABEL[task.effort]}
            {task.assignee_name && <> · {task.assignee_name}’s</>}
            {!task.assignee_name && task.claimable && <> · up for grabs</>}
            {task.is_snoozed && task.snoozed_until && (
              <> · {snoozedLabel(task.snoozed_until)} 😴</>
            )}
          </span>
          {/* The quiet waiting state (Phase 11): a fact, never a nag. */}
          {task.band === "waiting" && (
            <span className={styles.waiting}>{waitingLabel(task.zone_name)}</span>
          )}
          {/* Which clock schedules it (SPEC §4 lanes) — editable in place
              when the surface allows it (the Phase 11 review pass). */}
          {onTypeChanged ? (
            <select
              value={task.task_type}
              onClick={(e) => e.stopPropagation()}
              onChange={(e) => handleTypeChange(e.target.value as TaskType)}
              className={styles.typeSelect}
              aria-label={`Task type for ${task.name}`}
            >
              {TASK_TYPES.map((type) => (
                <option key={type} value={type}>
                  {TASK_TYPE_LABEL[type]}
                </option>
              ))}
            </select>
          ) : (
            <span className={styles.typeChip}>
              <Chip tone="neutral">{TASK_TYPE_LABEL[task.task_type]}</Chip>
            </span>
          )}
        </span>
        {!hideRoom && task.room_name && (
          <Chip tone={roomTone(task.room_id)}>{task.room_name}</Chip>
        )}
      </div>
      {onDone && (
        <button
          type="button"
          className={styles.doneButton}
          onClick={onDone}
          aria-label={`Mark ${task.name} done`}
        >
          ✓
        </button>
      )}
    </div>
  );
}
