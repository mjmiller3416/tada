const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/**
 * Fetch wrapper for the FastAPI backend. Always sends credentials so the
 * backend's httpOnly session cookie round-trips even though the frontend
 * and backend are different Railway services (different origins).
 */
export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.detail ?? `Request failed: ${res.status}`);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return res.json() as Promise<T>;
}

export type CurrentUser = {
  id: number;
  name: string;
  role: "owner" | "kid";
};

export function getCurrentUser() {
  return apiFetch<CurrentUser>("/api/auth/me");
}

export function login(pin: string) {
  return apiFetch<CurrentUser>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ pin }),
  });
}

export function logout() {
  return apiFetch<void>("/api/auth/logout", { method: "POST" });
}

export type PushSubscriptionPayload = {
  endpoint: string;
  keys: { p256dh: string; auth: string };
};

export function subscribeToPush(subscription: PushSubscriptionPayload) {
  return apiFetch<void>("/api/push/subscribe", {
    method: "POST",
    body: JSON.stringify(subscription),
  });
}

export function sendTestPush() {
  return apiFetch<void>("/api/push/test", { method: "POST" });
}
