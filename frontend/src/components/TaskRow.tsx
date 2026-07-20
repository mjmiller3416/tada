"use client";

import type { Task } from "@/lib/api";
import { EFFORT_LABEL, cadenceLabel, roomTone, snoozedLabel } from "@/lib/decay";
import { Chip } from "@/components/ui";
import DirtinessDot from "./DirtinessDot";
import styles from "./TaskRow.module.css";

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
};

/**
 * One task in a planning list (room detail / global view). Planning
 * surfaces show everything — including fresh and resting tasks — since
 * this is where she's organizing, not doing (SPEC §1).
 */
export default function TaskRow({
  task,
  hideRoom = false,
  onDone,
  onClick,
}: TaskRowProps) {
  return (
    <div className={styles.rowWrap}>
      <button type="button" className={styles.row} onClick={onClick}>
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
        </span>
        {!hideRoom && task.room_name && (
          <Chip tone={roomTone(task.room_id)}>{task.room_name}</Chip>
        )}
      </button>
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
