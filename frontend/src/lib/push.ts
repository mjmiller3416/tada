import { subscribeToPush } from "./api";

/** Converts a URL-safe base64 VAPID public key into the Uint8Array format
 * the Push API's applicationServerKey expects. */
function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; i++) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

/**
 * Registers the service worker (if not already), requests notification
 * permission, subscribes to push, and hands the subscription to the backend.
 * Throws if permission is denied or the browser lacks support.
 */
export async function enablePushNotifications(): Promise<void> {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    throw new Error("This browser does not support push notifications.");
  }

  const registration = await navigator.serviceWorker.register("/sw.js");
  await navigator.serviceWorker.ready;

  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    throw new Error("Notification permission was not granted.");
  }

  const vapidPublicKey = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY;
  if (!vapidPublicKey) {
    throw new Error("NEXT_PUBLIC_VAPID_PUBLIC_KEY is not configured.");
  }

  let subscription = await registration.pushManager.getSubscription();
  if (!subscription) {
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(vapidPublicKey) as BufferSource,
    });
  }

  const json = subscription.toJSON();
  if (!json.endpoint || !json.keys?.p256dh || !json.keys?.auth) {
    throw new Error("Push subscription is missing required fields.");
  }

  await subscribeToPush({
    endpoint: json.endpoint,
    keys: { p256dh: json.keys.p256dh, auth: json.keys.auth },
  });
}

/**
 * Whether this device is currently subscribed to push. Waits for the
 * service worker to be ACTIVE before reading — right after a force-close,
 * `getSubscription()` returns null until activation finishes, which made
 * the settings toggle read "off" while pushes were in fact arriving.
 * (Same `serviceWorker.ready` pattern the subscribe path above uses.)
 */
export async function isPushEnabled(): Promise<boolean> {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    return false;
  }
  if (!("Notification" in window) || Notification.permission !== "granted") {
    return false;
  }
  // Without a registration, `serviceWorker.ready` would wait forever.
  const registration = await navigator.serviceWorker.getRegistration();
  if (!registration) return false;
  const ready = await navigator.serviceWorker.ready;
  return (await ready.pushManager.getSubscription()) !== null;
}

/**
 * Belt-and-braces on app open: if notification permission is granted but
 * this device has lost its subscription (browser eviction, cleared
 * storage), quietly re-subscribe without her tapping anything. Does
 * nothing — and asks nothing — when permission was never granted.
 */
export async function ensurePushSubscription(): Promise<void> {
  try {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) return;
    if (!("Notification" in window) || Notification.permission !== "granted") {
      return;
    }
    const registration = await navigator.serviceWorker.register("/sw.js");
    await navigator.serviceWorker.ready;
    if (await registration.pushManager.getSubscription()) return;
    // Permission is already granted, so this runs prompt-free.
    await enablePushNotifications();
  } catch {
    // A background self-heal — never surface an error for it.
  }
}
