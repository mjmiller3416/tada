import { Button } from "tada-frontend";

/** The four voices: coral go-action, teal completion, quiet support, ghost. */
export const Variants = () => (
  <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
    <Button variant="primary">I have 15 minutes</Button>
    <Button variant="success">Done!</Button>
    <Button variant="secondary">Later today</Button>
    <Button variant="ghost">Skip for now</Button>
  </div>
);

export const Sizes = () => (
  <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
    <Button size="md">Add a task</Button>
    <Button size="lg">Start a session</Button>
  </div>
);

/** The big Done button as it appears at the bottom of a focus session. */
export const FullWidth = () => (
  <div style={{ width: 320 }}>
    <Button variant="success" size="lg" fullWidth>
      Done!
    </Button>
  </div>
);

export const Disabled = () => (
  <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
    <Button disabled>Saving…</Button>
    <Button variant="secondary" disabled>
      Later today
    </Button>
  </div>
);
