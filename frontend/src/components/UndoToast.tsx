"use client";

import { useEffect, useState } from "react";
import styles from "./UndoToast.module.css";

/** How long the toast lingers before quietly fading itself away. */
const LINGER_MS = 5000;
/** Matches --motion-base, so unmount waits for the fade-out to land. */
const FADE_MS = 240;

type UndoToastProps = {
  /** Called when she taps Undo; the toast dismisses itself right after. */
  onUndo: () => void;
  /** Called once the toast has faded or been used, so the parent drops it. */
  onGone: () => void;
};

/**
 * The post-completion Undo toast (Phase 9). A small, low-contrast pill
 * that appears only after the Done celebration has had its moment
 * (a CSS delay keeps it out of the burst), lingers a few seconds, and
 * fades on its own. It never gates the flow — in a focus session the
 * next card is already there and she can keep going straight past it.
 *
 * The label is exactly "Undo": a safety net, not an accusation — no
 * "Oops", no "Mistake?", and never a confirmation dialog.
 *
 * Re-mount per completion (key it) so the linger timer restarts.
 */
export default function UndoToast({ onUndo, onGone }: UndoToastProps) {
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    const linger = setTimeout(() => setLeaving(true), LINGER_MS);
    return () => clearTimeout(linger);
  }, []);

  useEffect(() => {
    if (!leaving) return;
    const fade = setTimeout(onGone, FADE_MS);
    return () => clearTimeout(fade);
  }, [leaving, onGone]);

  function handleUndo() {
    onUndo();
    onGone();
  }

  return (
    <div className={`${styles.toast} ${leaving ? styles.leaving : ""}`.trim()}>
      <button type="button" className={styles.undo} onClick={handleUndo}>
        Undo
      </button>
    </div>
  );
}
