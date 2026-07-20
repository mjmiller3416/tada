"use client";

import { useEffect, useMemo } from "react";
import styles from "./Celebration.module.css";

/*
 * Celebration components (SPEC §5) — the reward is in the doing:
 *  - Burst:    a small radial particle pop, played when Done is tapped.
 *  - Confetti: a full-screen shower for finishing a session.
 * Both are pure CSS animations reading only palette tokens; no libraries.
 */

const PIECE_COLORS = [
  "var(--color-coral)",
  "var(--color-teal)",
  "var(--color-purple)",
  "var(--tint-periwinkle-ink)",
  "var(--status-aging)",
];

type BurstProps = {
  /** While true the particles render and fly outward once. */
  play: boolean;
};

/**
 * A quick radial pop of particles from the center of its (position:
 * relative) parent. Toggle `play` on for ~--motion-slow, then off.
 */
export function Burst({ play }: BurstProps) {
  if (!play) return null;

  return (
    <span className={styles.burst} aria-hidden="true">
      {Array.from({ length: 10 }, (_, i) => (
        <span
          key={i}
          className={styles.particle}
          style={
            {
              "--angle": `${i * 36}deg`,
              background: PIECE_COLORS[i % PIECE_COLORS.length],
            } as React.CSSProperties
          }
        />
      ))}
    </span>
  );
}

type ConfettiPiece = {
  left: number;      /* % across the screen */
  delay: number;     /* seconds */
  duration: number;  /* seconds */
  drift: number;     /* horizontal sway in px */
  spin: number;      /* total rotation in deg */
  size: number;      /* px */
  color: string;
  round: boolean;
};

function makePieces(count: number): ConfettiPiece[] {
  return Array.from({ length: count }, (_, i) => ({
    left: Math.random() * 100,
    delay: Math.random() * 0.6,
    duration: 2 + Math.random() * 1.2,
    drift: (Math.random() - 0.5) * 160,
    spin: 360 + Math.random() * 540,
    size: 7 + Math.random() * 6,
    color: PIECE_COLORS[i % PIECE_COLORS.length],
    round: i % 3 === 0,
  }));
}

const CONFETTI_TOTAL_MS = 3800;

type ConfettiProps = {
  active: boolean;
  /** Called once the last piece has fallen, so the parent can reset. */
  onComplete?: () => void;
};

/** Full-screen confetti shower for session-complete celebrations. */
export function Confetti({ active, onComplete }: ConfettiProps) {
  /* Pieces are generated per activation, client-side only, so SSR
   * renders nothing and there is no hydration mismatch. */
  const pieces = useMemo(() => (active ? makePieces(90) : []), [active]);

  useEffect(() => {
    if (!active || !onComplete) return;
    const timer = setTimeout(onComplete, CONFETTI_TOTAL_MS);
    return () => clearTimeout(timer);
  }, [active, onComplete]);

  if (!active) return null;

  return (
    <div className={styles.confetti} aria-hidden="true">
      {pieces.map((p, i) => (
        <span
          key={i}
          className={`${styles.piece} ${p.round ? styles.round : ""}`.trim()}
          style={
            {
              left: `${p.left}%`,
              width: p.size,
              height: p.round ? p.size : p.size * 1.6,
              background: p.color,
              animationDelay: `${p.delay}s`,
              animationDuration: `${p.duration}s`,
              "--drift": `${p.drift}px`,
              "--spin": `${p.spin}deg`,
            } as React.CSSProperties
          }
        />
      ))}
    </div>
  );
}
