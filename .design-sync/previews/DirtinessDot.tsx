import { DirtinessDot } from "tada-frontend";

/** The four decay bands as bare dots — the signal at its smallest. */
export const AllBands = () => (
  <div style={{ display: "flex", gap: 20, alignItems: "center" }}>
    <DirtinessDot band="fresh" />
    <DirtinessDot band="aging" />
    <DirtinessDot band="due" />
    <DirtinessDot band="overdue" />
  </div>
);

/** Each band with its warm label — a gradient of care, never a scold. */
export const WithLabels = () => (
  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
    <DirtinessDot band="fresh" withLabel />
    <DirtinessDot band="aging" withLabel />
    <DirtinessDot band="due" withLabel />
    <DirtinessDot band="overdue" withLabel />
  </div>
);

/** In context: the room list on Today, dot + label per room. */
export const InRoomList = () => (
  <div style={{ width: 320, display: "flex", flexDirection: "column", gap: 12 }}>
    {(
      [
        ["Kitchen", "due"],
        ["Bathroom", "overdue"],
        ["Living room", "aging"],
        ["Bedroom", "fresh"],
      ] as const
    ).map(([room, band]) => (
      <div
        key={room}
        style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}
      >
        <span
          style={{
            fontSize: "var(--text-base)",
            fontWeight: "var(--weight-bold)" as React.CSSProperties["fontWeight"],
            color: "var(--color-ink)",
          }}
        >
          {room}
        </span>
        <DirtinessDot band={band} withLabel />
      </div>
    ))}
  </div>
);
