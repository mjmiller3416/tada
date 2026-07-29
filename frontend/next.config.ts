import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* The service worker and manifest are served as static files from
   * public/, which is all a PWA needs to be installable — no build
   * plugin required. */
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
