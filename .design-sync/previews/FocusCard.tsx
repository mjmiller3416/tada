import { FocusCard } from "tada-frontend";

const noop = () => {};
const phone: React.CSSProperties = { width: 360 };

/** Mid-session: room chip, big task name, estimate, dots at 3 of 5. */
export const MidSession = () => (
  <div style={phone}>
    <FocusCard
      taskName="Wipe the counters"
      estimatedMinutes={15}
      roomName="Kitchen"
      roomTone="mint"
      current={3}
      total={5}
      onDone={noop}
      onSkip={noop}
    />
  </div>
);

/** The inline supply flag — informative peach tint, never alarming. */
export const LowSupply = () => (
  <div style={phone}>
    <FocusCard
      taskName="Scrub the shower"
      estimatedMinutes={25}
      roomName="Bathroom"
      roomTone="lavender"
      supplyNote="heads up — you're low on bathroom spray"
      current={2}
      total={4}
      onDone={noop}
      onSkip={noop}
    />
  </div>
);

/** Room-less maintenance task: the chip slot collapses gracefully. */
export const NoRoom = () => (
  <div style={phone}>
    <FocusCard
      taskName="Change the furnace filter"
      estimatedMinutes={10}
      current={1}
      total={3}
      onDone={noop}
      onSkip={noop}
    />
  </div>
);

/** Last card of the session — every dot but one filled. */
export const LastTask = () => (
  <div style={phone}>
    <FocusCard
      taskName="Vacuum the rug"
      estimatedMinutes={20}
      roomName="Living room"
      roomTone="peach"
      current={5}
      total={5}
      onDone={noop}
      onSkip={noop}
    />
  </div>
);
