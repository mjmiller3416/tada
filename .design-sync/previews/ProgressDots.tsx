import { ProgressDots } from "tada-frontend";

/*
 * The focus-session progress signal: a row of tiny dots (teal = done,
 * coral = current). The component is legitimately small (~12px tall) —
 * labels alongside give it session context.
 */

const row: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "var(--space-4)",
};

const label: React.CSSProperties = {
  width: 104,
  fontSize: "var(--text-sm)",
  fontWeight: 700,
  color: "var(--color-ink-soft)",
};

/** A 5-task session from first task to finish line. */
export const SessionProgress = () => (
  <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
    <div style={row}>
      <span style={label}>Task 1 of 5</span>
      <ProgressDots total={5} current={1} />
    </div>
    <div style={row}>
      <span style={label}>Task 3 of 5</span>
      <ProgressDots total={5} current={3} />
    </div>
    <div style={row}>
      <span style={label}>Task 5 of 5</span>
      <ProgressDots total={5} current={5} />
    </div>
  </div>
);

/** A deep-clean Saturday: more dots, momentum well underway. */
export const LongSession = () => (
  <div style={row}>
    <span style={label}>Task 7 of 10</span>
    <ProgressDots total={10} current={7} />
  </div>
);
