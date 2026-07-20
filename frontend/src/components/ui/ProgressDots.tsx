import styles from "./ProgressDots.module.css";

type ProgressDotsProps = {
  /** Total tasks in the session. */
  total: number;
  /** 1-based position of the task currently showing. */
  current: number;
};

/**
 * The small progress signal for a focus session (SPEC §5): a row of dots —
 * momentum and a finish line, never the full list.
 */
export default function ProgressDots({ total, current }: ProgressDotsProps) {
  return (
    <div
      className={styles.dots}
      role="img"
      aria-label={`Task ${Math.min(current, total)} of ${total}`}
    >
      {Array.from({ length: total }, (_, i) => {
        const state =
          i + 1 < current ? styles.done : i + 1 === current ? styles.current : "";
        return <span key={i} className={`${styles.dot} ${state}`.trim()} />;
      })}
    </div>
  );
}
