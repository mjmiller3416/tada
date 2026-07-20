"use client";

import { useEffect, useRef, useState } from "react";
import Button from "./Button";
import Card from "./Card";
import Chip, { type ChipTone } from "./Chip";
import ProgressDots from "./ProgressDots";
import { Burst } from "./Celebration";
import styles from "./FocusCard.module.css";

/* Long enough for the Burst pop to land before the next card slides in. */
const DONE_POP_MS = 650;

type FocusCardProps = {
  taskName: string;
  estimatedMinutes: number;
  /** Room tag shown as a chip; omit for room-less tasks. */
  roomName?: string;
  roomTone?: ChipTone;
  /** 1-based position in the session, for the small progress signal. */
  current: number;
  total: number;
  /** Called after the brief Done celebration finishes. */
  onDone: () => void;
  /** Called immediately — skipping is free and quiet, no fanfare. */
  onSkip: () => void;
};

/**
 * The one-task-at-a-time card at the heart of a focus session (SPEC §5):
 * room tag, big task name, time estimate, a big Done, a quiet Skip, and
 * dots for momentum — never the full list. Tapping Done plays a small
 * particle pop, then advances.
 *
 * Re-mount per task (key it by task id) so the entrance animation plays
 * on every card.
 */
export default function FocusCard({
  taskName,
  estimatedMinutes,
  roomName,
  roomTone = "periwinkle",
  current,
  total,
  onDone,
  onSkip,
}: FocusCardProps) {
  const [celebrating, setCelebrating] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  function handleDone() {
    if (celebrating) return;
    setCelebrating(true);
    timerRef.current = setTimeout(() => {
      setCelebrating(false);
      onDone();
    }, DONE_POP_MS);
  }

  return (
    <Card padding="lg" className={styles.card}>
      <div className={styles.top}>
        {roomName ? <Chip tone={roomTone}>{roomName}</Chip> : <span />}
        <ProgressDots total={total} current={current} />
      </div>

      <h2 className={styles.taskName}>{taskName}</h2>
      <p className={styles.estimate}>about {estimatedMinutes} min</p>

      <div className={styles.doneWrap}>
        <Burst play={celebrating} />
        <Button
          variant="success"
          size="lg"
          fullWidth
          onClick={handleDone}
          disabled={celebrating}
        >
          Done!
        </Button>
      </div>

      <Button
        variant="ghost"
        size="md"
        fullWidth
        onClick={onSkip}
        disabled={celebrating}
      >
        Skip for now
      </Button>
    </Card>
  );
}
