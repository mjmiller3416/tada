import { AppShell } from "tada-frontend";

/*
 * The phone frame. AppShell's bottom nav is position: fixed, so each cell
 * wraps the shell in a phone-sized container with a transform — that makes
 * the wrapper the containing block for fixed descendants and keeps the nav
 * inside the frame. next/navigation is shimmed in this bundle, so no nav
 * item shows its active state; that's expected.
 */

const nav = [
  { href: "/", label: "Home", icon: "🏠" },
  { href: "/rooms", label: "Rooms", icon: "🧹" },
  { href: "/sessions", label: "Sessions", icon: "⏱️" },
  { href: "/settings", label: "Settings", icon: "⚙️" },
];

const phone: React.CSSProperties = {
  position: "relative",
  width: 390,
  height: 640,
  overflow: "hidden",
  borderRadius: 28,
  border: "1px solid var(--color-line)",
  boxShadow: "0 10px 28px rgba(58, 40, 35, 0.14)",
  /* Contain the fixed bottom nav inside the phone frame. */
  transform: "translateZ(0)",
};

const roomCard: React.CSSProperties = {
  background: "var(--color-surface)",
  border: "1px solid var(--color-line)",
  borderRadius: "var(--radius-card)",
  padding: "var(--space-4)",
  marginBottom: "var(--space-3)",
};

const roomName: React.CSSProperties = {
  fontWeight: 800,
  fontSize: "var(--text-lg)",
  marginBottom: "var(--space-1)",
};

const roomMeta: React.CSSProperties = {
  color: "var(--color-ink-soft)",
  fontSize: "var(--text-sm)",
};

/** The everyday frame: title bar, room list content, four-item bottom nav. */
export const RoomsScreen = () => (
  <div style={phone}>
    <AppShell title="Rooms" nav={nav}>
      <div style={roomCard}>
        <div style={roomName}>🍳 Kitchen</div>
        <div style={roomMeta}>3 tasks due · wiped down 2 days ago</div>
      </div>
      <div style={roomCard}>
        <div style={roomName}>🛁 Bathroom</div>
        <div style={roomMeta}>Fresh — scrubbed this morning</div>
      </div>
      <div style={roomCard}>
        <div style={roomName}>🛋️ Living room</div>
        <div style={roomMeta}>2 tasks aging · vacuum the rug soon</div>
      </div>
      <div style={roomCard}>
        <div style={roomName}>🛏️ Bedroom</div>
        <div style={roomMeta}>1 task overdue · change the sheets</div>
      </div>
    </AppShell>
  </div>
);

/** Nav omitted for full-screen flows (login, focus sessions). */
export const FullScreenFlow = () => (
  <div style={phone}>
    <AppShell title="Welcome back">
      <p style={{ margin: "0 0 var(--space-4)", color: "var(--color-ink-soft)" }}>
        Who's cleaning today?
      </p>
      <div style={roomCard}>
        <div style={roomName}>🧑‍🍳 Mom</div>
        <div style={roomMeta}>Finished the Kitchen session yesterday</div>
      </div>
      <div style={roomCard}>
        <div style={roomName}>🧒 Maya</div>
        <div style={roomMeta}>2 chores waiting — feed the cat, water the plants</div>
      </div>
      <div style={roomCard}>
        <div style={roomName}>👦 Theo</div>
        <div style={roomMeta}>All caught up 🎉</div>
      </div>
    </AppShell>
  </div>
);
