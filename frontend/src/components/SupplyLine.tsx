"use client";

import { useState } from "react";
import type { SupplyBrief, Task } from "@/lib/api";
import { supplyNote } from "@/lib/supplies";
import SupplyCheck from "./SupplyCheck";
import styles from "./SupplyLine.module.css";

type SupplyLineProps = {
  task: Task;
  /** Passed straight through to SupplyCheck — see its docs. */
  onChanged: (supply: SupplyBrief) => void;
};

/**
 * The supplies doorway on a task card (SPEC §6 Supplies). One line of
 * the card, three states:
 *
 *  - everything stocked  → a quiet "Running low on anything?" whisper,
 *                          the same weight as the card's other labels
 *  - something low/out   → the peach heads-up, as before — now tappable
 *  - tapped              → SupplyCheck, the status chips inline
 *
 * Renders nothing for a task with no supplies linked, so those cards look
 * exactly as they always have. Status stays manual; this just puts the
 * tap where she notices instead of on another screen.
 */
export default function SupplyLine({ task, onChanged }: SupplyLineProps) {
  const [open, setOpen] = useState(false);

  if (task.supplies.length === 0) return null;

  if (open) {
    return (
      <SupplyCheck
        supplies={task.supplies}
        onChanged={onChanged}
        onClose={() => setOpen(false)}
      />
    );
  }

  const note = supplyNote(task);
  if (note) {
    return (
      <button type="button" className={styles.note} onClick={() => setOpen(true)}>
        🧴 {note}
      </button>
    );
  }

  return (
    <button type="button" className={styles.whisper} onClick={() => setOpen(true)}>
      🧴 <span className={styles.whisperText}>Running low on anything?</span>
    </button>
  );
}
