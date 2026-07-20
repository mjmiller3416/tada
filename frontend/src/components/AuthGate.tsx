"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getCurrentUser, type CurrentUser } from "@/lib/api";

type State =
  | { status: "loading" }
  | { status: "authenticated"; user: CurrentUser }
  | { status: "unauthenticated" };

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
      .catch(() => {
        if (!cancelled) setState({ status: "unauthenticated" });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const kidBlocked =
    ownerOnly && state.status === "authenticated" && state.user.role !== "owner";

  useEffect(() => {
    if (state.status === "unauthenticated") {
      router.replace("/login");
    } else if (kidBlocked) {
      router.replace("/");
    }
  }, [state.status, kidBlocked, router]);

  if (state.status !== "authenticated" || kidBlocked) {
    return null;
  }

  return <>{children(state.user)}</>;
}
