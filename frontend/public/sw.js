// Tada service worker — Phase 0: push notifications only.
// Grows in later phases (offline caching, etc.) as real needs show up.

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { title: "Tada", body: event.data ? event.data.text() : "" };
  }

  const title = data.title || "Tada";
  const options = {
    body: data.body || "",
    icon: "/icons/icon-192.png",
    badge: "/icons/icon-192.png",
  };
  // Notifications sharing a tag replace each other instead of stacking —
  // the backend sends tag "daily-nudge" on the morning nudge so missed
  // days never pile up in the tray.
  if (data.tag) {
    options.tag = data.tag;
  }

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((clientList) => {
        for (const client of clientList) {
          if ("focus" in client) return client.focus();
        }
        if (self.clients.openWindow) return self.clients.openWindow("/");
      }),
  );
});
