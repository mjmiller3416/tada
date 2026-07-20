import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* Phase 0: no special config yet. The service worker and manifest are
   * served as static files from public/, which is all a PWA needs to be
   * installable — no build plugin required. */
};

export default nextConfig;
