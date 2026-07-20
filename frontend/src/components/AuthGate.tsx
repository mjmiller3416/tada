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
 */
export default function AuthGate({
  children,
}: {
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

  useEffect(() => {
    if (state.status === "unauthenticated") {
      router.replace("/login");
    }
  }, [state.status, router]);

  if (state.status !== "authenticated") {
    return null;
  }

  return <>{children(state.user)}</>;
}
