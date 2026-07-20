"use client";

import { useEffect } from "react";

/** Registers the service worker as soon as the app loads, independent of
 * the push-subscribe flow, so the PWA is installable right away. */
export default function ServiceWorkerRegister() {
  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch((err) => {
        console.error("Service worker registration failed", err);
      });
    }
  }, []);

  return null;
}
