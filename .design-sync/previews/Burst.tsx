import { Burst } from "tada-frontend";

/*
 * The Done pop: a one-shot 450ms radial particle burst played from the
 * center of its position: relative parent when Done is tapped.
 */

/* The just-tapped Done check: compact and circular so the 56px particle
 * ring clears its silhouette instead of hiding behind a wide pill. */
const doneCheck: React.CSSProperties = {
  width: 48,
  height: 48,
  display: "grid",
  placeItems: "center",
  background: "var(--color-teal)",
  color: "#fff",
  fontWeight: 800,
  fontSize: "var(--text-xl)",
  borderRadius: "var(--radius-pill)",
  boxShadow: "0 4px 12px rgba(29, 158, 117, 0.35)",
};

/**
 * The burst as it fires the moment Done is tapped in a focus session.
 * The one-shot 450ms animation is posed mid-flight (paused + negative
 * delay) so the capture can see the particles; live it plays through.
 * The wrapper zoom is a close-up — the particles are 8px at 1x.
 */
export const DonePop = () => (
  <div style={{ zoom: 1.5 } as React.CSSProperties}>
    <div
      className="freeze-burst"
      style={{
        position: "relative",
        width: 180,
        height: 160,
        display: "grid",
        placeItems: "center",
      }}
    >
      <style>{`
        .freeze-burst span {
          animation-play-state: paused !important;
          animation-delay: -0.12s !important;
        }
      `}</style>
      <div style={doneCheck}>✓</div>
      <Burst play />
    </div>
  </div>
);
