import { Confetti } from "tada-frontend";

/*
 * Session-complete confetti shower. The component is position: fixed
 * full-screen; the wrapper's transform makes it the containing block for
 * fixed descendants so the shower stays inside this card.
 */

/*
 * The 2–3.2s fall animations are posed mid-shower (paused + banded
 * negative delays via nth-child) so the capture shows pieces spread from
 * the top of the card to well down it; live the shower plays through.
 */
export const SessionComplete = () => (
  <div
    className="freeze-confetti"
    style={{
      position: "relative",
      width: 380,
      height: 360,
      overflow: "hidden",
      borderRadius: "var(--radius-card)",
      border: "1px solid var(--color-line)",
      background: "var(--color-bg)",
      display: "grid",
      placeItems: "center",
      /* Contain the fixed full-screen shower inside this card. */
      transform: "translateZ(0)",
    }}
  >
    <style>{`
      .freeze-confetti span {
        animation-play-state: paused !important;
        animation-delay: -0.25s !important;
      }
      .freeze-confetti span:nth-child(3n) {
        animation-delay: -0.75s !important;
      }
      .freeze-confetti span:nth-child(3n + 1) {
        animation-delay: -1.25s !important;
      }
    `}</style>
    <div style={{ textAlign: "center", padding: "var(--space-5)" }}>
      <div style={{ fontSize: "var(--text-2xl)", fontWeight: 800, marginBottom: "var(--space-2)" }}>
        Ta-da! 🎉
      </div>
      <div style={{ color: "var(--color-ink-soft)", fontSize: "var(--text-base)" }}>
        Kitchen session complete — 5 tasks done in 22 minutes
      </div>
    </div>
    <Confetti active />
  </div>
);
