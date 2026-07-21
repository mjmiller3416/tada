import { Button, Card, Chip } from "tada-frontend";

const heading: React.CSSProperties = {
  margin: 0,
  fontSize: "var(--text-lg)",
  fontWeight: "var(--weight-bold)" as React.CSSProperties["fontWeight"],
  color: "var(--color-ink)",
};

const soft: React.CSSProperties = {
  margin: "var(--space-1) 0 0",
  fontSize: "var(--text-sm)",
  color: "var(--color-ink-soft)",
};

/** The default surface (md padding) — a quiet room summary block. */
export const Default = () => (
  <div style={{ width: 360 }}>
    <Card>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <h3 style={heading}>Living room</h3>
        <Chip tone="peach">6 tasks</Chip>
      </div>
      <p style={soft}>Mostly sparkling — two things could use some love.</p>
    </Card>
  </div>
);

/** Large padding for hero moments, like the session invitation on Today. */
export const PaddingLarge = () => (
  <div style={{ width: 360 }}>
    <Card padding="lg">
      <h3 style={{ ...heading, fontSize: "var(--text-xl)" }}>Got a spare 15 minutes?</h3>
      <p style={{ ...soft, fontSize: "var(--text-base)", margin: "var(--space-2) 0 var(--space-4)" }}>
        Three quick wins are ready — the house will thank you.
      </p>
      <Button variant="primary" size="lg" fullWidth>
        I have 15 minutes
      </Button>
    </Card>
  </div>
);

/** padding="none" lets list rows manage their own padding, flush to the edge. */
export const PaddingNone = () => (
  <div style={{ width: 360 }}>
    <Card padding="none">
      {[
        ["Wipe the counters", "Kitchen · about 15 min"],
        ["Scrub the shower", "Bathroom · about 25 min"],
        ["Vacuum the rug", "Living room · about 20 min"],
      ].map(([name, meta], i) => (
        <div
          key={name}
          style={{
            padding: "var(--space-3) var(--space-4)",
            borderTop: i === 0 ? "none" : "1px solid var(--color-line)",
          }}
        >
          <p style={{ ...heading, fontSize: "var(--text-base)" }}>{name}</p>
          <p style={soft}>{meta}</p>
        </div>
      ))}
    </Card>
  </div>
);
