import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* The service worker and manifest are served as static files from
   * public/, which is all a PWA needs to be installable — no build
   * plugin required. */
  async rewrites() {
    // Proxies browser calls to the backend through this server instead of
    // letting the browser hit it cross-origin. The frontend and backend
    // are separate Railway services (different subdomains), which makes
    // the session cookie cross-site — iOS Safari, especially in
    // standalone/home-screen PWA mode, silently refuses to persist those
    // (ITP), so login appears to succeed but the session never sticks.
    // Routing through here means the browser only ever talks to its own
    // origin, so the cookie is first-party.
    const backendUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
  async redirects() {
    return [
      // Phase 6 renamed Packing -> Lists. Keep the old URLs alive so
      // her home-screen shortcut (and any stale tab) still lands right.
      // Not `permanent`: browsers cache 308s aggressively, and we may
      // want this path back someday.
      {
        source: "/packing",
        destination: "/lists",
        permanent: false,
      },
      {
        source: "/packing/:id",
        destination: "/lists/:id",
        permanent: false,
      },
    ];
  },
};

export default nextConfig;
