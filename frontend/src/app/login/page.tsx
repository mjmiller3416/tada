"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [pin, setPin] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(pin);
      router.replace("/");
    } catch {
      setError("That PIN didn't work — try again.");
      setPin("");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main
      style={{
        padding: 24,
        maxWidth: 320,
        margin: "10vh auto 0",
        textAlign: "center",
      }}
    >
      <h1>Tada</h1>
      <form onSubmit={handleSubmit}>
        <input
          type="password"
          inputMode="numeric"
          autoFocus
          value={pin}
          onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
          placeholder="Enter your PIN"
          style={{
            fontSize: 24,
            textAlign: "center",
            letterSpacing: 8,
            padding: "12px 16px",
            width: "100%",
            boxSizing: "border-box",
          }}
        />
        <button
          type="submit"
          disabled={submitting || pin.length === 0}
          style={{ marginTop: 16, width: "100%", padding: "12px 16px" }}
        >
          Log in
        </button>
      </form>
      {error && <p style={{ color: "crimson" }}>{error}</p>}
    </main>
  );
}
