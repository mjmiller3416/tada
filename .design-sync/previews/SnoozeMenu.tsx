import { Card, SnoozeMenu } from "tada-frontend";

const noop = () => {};

/** The gentle snooze options on their own — nothing is "missed" here. */
export const Menu = () => (
  <div style={{ width: 360 }}>
    <SnoozeMenu onPick={noop} onCancel={noop} />
  </div>
);

/** In place: the menu replaces the Done/Skip actions inside a task card. */
export const InTaskCard = () => (
  <div style={{ width: 360 }}>
    <Card padding="lg">
      <h2
        style={{
          margin: 0,
          fontSize: "var(--text-2xl)",
          fontWeight: "var(--weight-bold)" as React.CSSProperties["fontWeight"],
          color: "var(--color-ink)",
          lineHeight: 1.2,
        }}
      >
        Mop the floors
      </h2>
      <p
        style={{
          margin: "var(--space-1) 0 0",
          fontSize: "var(--text-base)",
          color: "var(--color-ink-soft)",
        }}
      >
        about 30 min
      </p>
      <SnoozeMenu onPick={noop} onCancel={noop} />
    </Card>
  </div>
);
