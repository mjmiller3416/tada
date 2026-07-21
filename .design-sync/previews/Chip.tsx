import { Chip } from "tada-frontend";

const wrap: React.CSSProperties = {
  display: "flex",
  gap: 8,
  flexWrap: "wrap",
  alignItems: "center",
};

/** Every tint — rooms cycle the bridge tints; coral/teal mean go/done. */
export const Tones = () => (
  <div style={wrap}>
    <Chip tone="peach">Kitchen</Chip>
    <Chip tone="berry">Bathroom</Chip>
    <Chip tone="lavender">Bedroom</Chip>
    <Chip tone="periwinkle">Office</Chip>
    <Chip tone="mint">Living room</Chip>
    <Chip tone="neutral">Hallway</Chip>
    <Chip tone="coral">15 min</Chip>
    <Chip tone="teal">Done today</Chip>
  </div>
);

/** With onClick the chip renders as a tappable button (category shortcuts). */
export const Tappable = () => (
  <div style={wrap}>
    <Chip tone="mint" onClick={() => {}}>
      Quick wins
    </Chip>
    <Chip tone="lavender" onClick={() => {}}>
      Deep cleans
    </Chip>
    <Chip tone="peach" onClick={() => {}}>
      Guest-ready
    </Chip>
  </div>
);
