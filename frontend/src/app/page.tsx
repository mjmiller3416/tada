"use client";

import { useRouter } from "next/navigation";
import AuthGate from "@/components/AuthGate";
import PushSubscribeButton from "@/components/PushSubscribeButton";
import TestPushButton from "@/components/TestPushButton";
import { logout } from "@/lib/api";

/**
 * Phase 0 placeholder home screen. No feature UI yet (Phase 1) and no
 * design system yet (Phase 0.5) — this page exists only to prove that
 * auth and push work end to end.
 */
export default function HomePage() {
  const router = useRouter();

  return (
    <AuthGate>
      {(user) => (
        <main style={{ padding: 24, maxWidth: 420, margin: "0 auto" }}>
          <h1>Hi, {user.name}</h1>
          <p>Phase 0 shell — auth and push are wired up.</p>

          <section style={{ marginTop: 24 }}>
            <PushSubscribeButton />
          </section>

          <section style={{ marginTop: 16 }}>
            <TestPushButton />
          </section>

          <section style={{ marginTop: 32 }}>
            <button
              onClick={() => logout().finally(() => router.replace("/login"))}
            >
              Log out
            </button>
          </section>
        </main>
      )}
    </AuthGate>
  );
}
