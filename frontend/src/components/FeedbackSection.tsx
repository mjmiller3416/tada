"use client";

import { useRef, useState } from "react";
import { useFeedbackForm } from "@/hooks/useFeedbackForm";
import type { FeedbackCategory } from "@/lib/api";
import { Button, Card } from "@/components/ui";
import styles from "./FeedbackSection.module.css";

const CATEGORIES: FeedbackCategory[] = ["Something's broken", "Idea"];

/**
 * "Something on your mind?" — a one-tap path from Settings to a GitHub
 * issue on the Tada repo, so a bug or idea doesn't just live in a text
 * message. Settings-only: no home card, no nav entry, no floating
 * button (the one-new-element rule from Phase 5 still holds).
 *
 * Not guarded against guest/Chaos mode here — that's a session-flow
 * concept entirely separate from Settings (an owner-gated Chromebook
 * surface), so it never overlaps with this section in practice.
 */
export default function FeedbackSection() {
  const form = useFeedbackForm();
  const [toast, setToast] = useState<string | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  function showToast(text: string) {
    setToast(text);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 3000);
  }

  async function handleSubmit() {
    const success = await form.handleSubmit();
    showToast(success ? "Got it — thanks!" : "That didn’t go through — try again in a bit.");
  }

  return (
    <Card className={styles.section}>
      <h2 className={styles.heading}>Something on your mind?</h2>
      <p className={styles.help}>
        Tell Mitchell what’s not working, or what would make this better.
      </p>

      <div className={styles.toast} aria-live="polite">
        {toast ?? " "}
      </div>

      <div className={styles.categories}>
        {CATEGORIES.map((cat) => (
          <button
            key={cat}
            type="button"
            className={`${styles.categoryOption} ${
              form.category === cat ? styles.selected : ""
            }`.trim()}
            onClick={() => form.setCategory(cat)}
          >
            {cat}
          </button>
        ))}
      </div>

      <textarea
        className={styles.textarea}
        placeholder="What happened, or what were you hoping for?"
        value={form.message}
        onChange={(e) => form.setMessage(e.target.value)}
        rows={4}
        maxLength={5000}
        aria-label="Your message"
      />

      <Button
        variant="primary"
        fullWidth
        disabled={!form.canSubmit}
        onClick={handleSubmit}
      >
        {form.isSubmitting ? "Sending…" : "Send it"}
      </Button>
    </Card>
  );
}
