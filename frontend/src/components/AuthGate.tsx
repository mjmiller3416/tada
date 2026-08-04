"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, getCurrentUser, type CurrentUser } from "@/lib/api";
import { ensurePushSubscription } from "@/lib/push";

// Once per app load, not per page — the self-heal below only needs to
// run when the app opens.
let pushEnsuredThisLoad = false;

type State =
  | { status: "loading" }
  | { status: "authenticated"; user: CurrentUser }
  | { status: "unauthenticated" }
  // A 401 means "no session yet" — expected, redirect quietly. Anything
  // else (network failure, 5xx, a session that didn't stick) is a real
  // failure and must say so instead of silently bouncing to /login.
  | { status: "session_error" };

/**
 * Checks the session client-side (not via Next.js middleware) because the
 * session cookie belongs to the backend's origin — a different Railway
 * service — and is never visible to the frontend server.
 *
 * `ownerOnly` marks the planning/settings surfaces: a kid landing there
 * is quietly sent home to their chores (the backend enforces the same
 * rule on the API).
 */
export default function AuthGate({
  ownerOnly = false,
  children,
}: {
  ownerOnly?: boolean;
  children: (user: CurrentUser) => React.ReactNode;
}) {
  const router = useRouter();
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    getCurrentUser()
      .then((user) => {
        if (!cancelled) setState({ status: "authenticated", user });
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) {
          setState({ status: "unauthenticated" });
        } else {
          setState({ status: "session_error" });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Belt-and-braces (Phase 4.5): if permission is granted but the
  // subscription has been lost, quietly re-subscribe on app open —
  // needs an authenticated session, hence it lives here.
  useEffect(() => {
    if (state.status === "authenticated" && !pushEnsuredThisLoad) {
      pushEnsuredThisLoad = true;
      void ensurePushSubscription();
    }
  }, [state.status]);

  const kidBlocked =
    ownerOnly && state.status === "authenticated" && state.user.role !== "owner";

  useEffect(() => {
    if (state.status === "unauthenticated") {
      router.replace("/login");
    } else if (state.status === "session_error") {
      router.replace("/login?error=session");
    } else if (kidBlocked) {
      router.replace("/");
    }
  }, [state.status, kidBlocked, router]);

  if (state.status !== "authenticated" || kidBlocked) {
    return null;
  }

  return <>{children(state.user)}</>;
}
