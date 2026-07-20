"use client";

import { useState } from "react";
import { sendTestPush } from "@/lib/api";

/**
 * TEMPORARY — Phase 0 only. Proves the auth -> subscribe -> backend -> push
 * pipeline works end to end. Remove this component (and the backend
 * /api/push/test route) once Phase 0 verification is complete.
 */
export default function TestPushButton() {
  const [status, setStatus] = useState<"idle" | "working" | "sent" | "error">(
    "idle",
  );
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    setStatus("working");
    setError(null);
    try {
      await sendTestPush();
      setStatus("sent");
    } catch (err) {
      setStatus("error");
      setError(err instanceof Error ? err.message : "Something went wrong.");
    }
  }

  return (
    <div>
      <button onClick={handleClick} disabled={status === "working"}>
        Send test push (temporary — Phase 0 only)
      </button>
      {status === "sent" && <p>Sent. Check your phone.</p>}
      {error && <p style={{ color: "crimson" }}>{error}</p>}
    </div>
  );
}
