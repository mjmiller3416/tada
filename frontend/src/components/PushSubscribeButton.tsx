"use client";

import { useState } from "react";
import { enablePushNotifications } from "@/lib/push";
import { Button } from "@/components/ui";

export default function PushSubscribeButton() {
  const [status, setStatus] = useState<"idle" | "working" | "done" | "error">(
    "idle",
  );
  const [error, setError] = useState<string | null>(null);

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
        disabled={status === "working"}
        fullWidth
      >
        {status === "done"
          ? "Notifications enabled ✓"
          : status === "working"
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
