"use client";

import { useState } from "react";
import {
  submitFeedback,
  type FeedbackCategory,
  type FeedbackMetadata,
} from "@/lib/api";

const MIN_MESSAGE_LENGTH = 10;
const MAX_MESSAGE_LENGTH = 5000;

/** Gathered fresh at submit time, every report (the "Something on your
 * mind?" section's checklist) — omit a key entirely rather than send a
 * made-up value for it (no app_version yet; there's no build id to read). */
function collectMetadata(): FeedbackMetadata {
  return {
    page_url: window.location.pathname,
    viewport: `${window.innerWidth}x${window.innerHeight}`,
    user_agent: navigator.userAgent,
    display_mode: window.matchMedia("(display-mode: standalone)").matches
      ? "standalone"
      : "browser",
    notification_permission: "Notification" in window ? Notification.permission : null,
    service_worker_state:
      "serviceWorker" in navigator
        ? (navigator.serviceWorker.controller?.state ?? "none")
        : "none",
  };
}

/**
 * All the state and logic behind the Settings feedback section — the
 * component stays a thin consumer. `canSubmit` requires a chosen
 * category AND a trimmed message of at least ten characters.
 */
export function useFeedbackForm() {
  const [category, setCategory] = useState<FeedbackCategory | null>(null);
  const [message, setMessage] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const trimmedLength = message.trim().length;
  const canSubmit = category !== null && trimmedLength >= MIN_MESSAGE_LENGTH && !isSubmitting;

  function reset() {
    setCategory(null);
    setMessage("");
  }

  async function handleSubmit(): Promise<boolean> {
    if (!canSubmit || category === null) return false;
    setIsSubmitting(true);
    try {
      await submitFeedback({
        category,
        message: message.trim(),
        metadata: collectMetadata(),
      });
      reset();
      return true;
    } catch {
      return false;
    } finally {
      setIsSubmitting(false);
    }
  }

  return {
    category,
    setCategory,
    message,
    setMessage,
    isSubmitting,
    canSubmit,
    remainingChars: MAX_MESSAGE_LENGTH - message.length,
    handleSubmit,
    reset,
  };
}
