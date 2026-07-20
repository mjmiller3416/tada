"use client";

import { useState } from "react";
import { enablePushNotifications } from "@/lib/push";

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
      <button onClick={handleClick} disabled={status === "working"}>
        {status === "done" ? "Notifications enabled" : "Enable notifications"}
      </button>
      {error && <p style={{ color: "crimson" }}>{error}</p>}
    </div>
  );
}
