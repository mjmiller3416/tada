/**
 * design-sync shim for next/navigation — just enough for presentational
 * renders. usePathname reads the real location so AppShell's active-nav
 * highlighting still works in rendered designs.
 */
export function usePathname(): string {
  return typeof window !== "undefined" ? window.location.pathname : "/";
}

export function useRouter() {
  const noop = () => {};
  return {
    push: noop,
    replace: noop,
    back: noop,
    forward: noop,
    refresh: noop,
    prefetch: noop,
  };
}

export function useSearchParams(): URLSearchParams {
  return new URLSearchParams(
    typeof window !== "undefined" ? window.location.search : "",
  );
}
