"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { login } from "@/lib/api";
import { Button, Card } from "@/components/ui";
import styles from "./login.module.css";

export default function LoginPage() {
  const router = useRouter();
  const [pin, setPin] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // AuthGate sends us here (not a silent bounce) when a session check
  // failed for a reason other than "never logged in" — surface that
  // instead of leaving her staring at a blank login screen. Read via
  // window.location rather than useSearchParams so this page doesn't need
  // a Suspense boundary.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("error") === "session") {
      setError("Something went wrong loading your session — try logging in again.");
    }
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(pin);
      router.replace("/");
    } catch {
      setError("That PIN didn’t work — try again.");
      setPin("");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className={styles.page}>
      <h1 className={styles.wordmark}>Tada</h1>
      <p className={styles.tagline}>Your home’s cleaning coach ✨</p>

      <Card padding="lg" className={styles.card}>
        <form onSubmit={handleSubmit} className={styles.form}>
          <label htmlFor="pin" className={styles.label}>
            Enter your PIN
          </label>
          <input
            id="pin"
            type="password"
            inputMode="numeric"
            autoFocus
            value={pin}
            onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
            placeholder="••••"
            className={styles.pin}
          />
          <Button
            type="submit"
            variant="primary"
            size="lg"
            fullWidth
            disabled={submitting || pin.length === 0}
          >
            {submitting ? "One sec…" : "Let’s go"}
          </Button>
        </form>
        {error && <p className={styles.error}>{error}</p>}
      </Card>
    </main>
  );
}
