"use client";

import type { SnoozeOption } from "@/lib/api";
import { Button } from "@/components/ui";
import styles from "./SnoozeMenu.module.css";

type SnoozeMenuProps = {
  onPick: (option: Exclude<SnoozeOption, "wake">) => void;
  onCancel: () => void;
};

/**
 * The decay-aware snooze options (SPEC §6). Deliberately gentle framing:
 * snoozing is a normal, fine thing to do — the task just rests and
 * resurfaces on its own, nothing is marked done and nothing is "missed".
 */
export default function SnoozeMenu({ onPick, onCancel }: SnoozeMenuProps) {
  return (
    <div className={styles.menu}>
      <p className={styles.hint}>No problem — when should it come back?</p>
      <div className={styles.options}>
        <Button variant="secondary" onClick={() => onPick("later_today")}>
          Later today
        </Button>
        <Button variant="secondary" onClick={() => onPick("tomorrow")}>
          Tomorrow
        </Button>
        <Button variant="secondary" onClick={() => onPick("few_days")}>
          In a few days
        </Button>
      </div>
      <Button variant="ghost" onClick={onCancel}>
        Never mind
      </Button>
    </div>
  );
}
