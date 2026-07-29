"use client";

import { useEffect, useState } from "react";
import { enablePushNotifications, isPushEnabled } from "@/lib/push";
import { Button } from "@/components/ui";

export default function PushSubscribeButton() {
  const [status, setStatus] = useState<
    "checking" | "idle" | "working" | "done" | "error"
  >("checking");
  const [error, setError] = useState<string | null>(null);

  // Read the real subscription state on mount (isPushEnabled waits for
  // the service worker to be active, so a fresh open after a force-close
  // no longer reads as "off").
  useEffect(() => {
    let cancelled = false;
    isPushEnabled()
      .then((enabled) => {
        if (!cancelled) setStatus(enabled ? "done" : "idle");
      })
      .catch(() => {
        if (!cancelled) setStatus("idle");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleClick() {
    setStatus("working");
    setError(null);
    try {
      await enablePushNotifications();
      setStatus("done");
    } catch (err) {
      setStatus("error");
      setError(err instanceof Error ? err.message : "Something went wrong.");
    }
  }

  return (
    <div>
      <Button
        variant={status === "done" ? "secondary" : "primary"}
        onClick={handleClick}
        disabled={status === "working" || status === "checking"}
        fullWidth
      >
        {status === "done"
          ? "Notifications enabled ✓"
          : status === "working" || status === "checking"
            ? "One sec…"
            : "Enable notifications"}
      </Button>
      {error && (
        <p style={{ color: "var(--status-overdue)", fontSize: "var(--text-sm)" }}>
          {error}
        </p>
      )}
    </div>
  );
}
