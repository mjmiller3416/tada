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

/* ---- Auth ---- */

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

/* ---- Push ---- */

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

/* ---- Tasks & decay (Phase 1) ---- */

export type Band = "fresh" | "aging" | "due" | "overdue";
export type Effort = "quick" | "deep";
export type SnoozeOption = "later_today" | "tomorrow" | "few_days" | "wake";

export type Task = {
  id: number;
  name: string;
  room_id: number | null;
  room_name: string | null;
  category: string;
  cadence_days: number;
  estimated_minutes: number;
  effort: Effort;
  guest_facing: boolean;
  last_done_at: string | null;
  snoozed_until: string | null;
  is_snoozed: boolean;
  is_active: boolean;
  notes: string | null;
  ratio: number;
  band: Band;
};

export type TaskInput = {
  name: string;
  room_id: number | null;
  cadence_days: number;
  estimated_minutes: number;
  effort: Effort;
  notes?: string | null;
};

export function getTasks(params?: {
  room_id?: number;
  effort?: Effort;
  include_inactive?: boolean;
}) {
  const query = new URLSearchParams();
  if (params?.room_id != null) query.set("room_id", String(params.room_id));
  if (params?.effort) query.set("effort", params.effort);
  if (params?.include_inactive) query.set("include_inactive", "true");
  const qs = query.toString();
  return apiFetch<Task[]>(`/api/tasks${qs ? `?${qs}` : ""}`);
}

export function createTask(input: TaskInput) {
  return apiFetch<Task>("/api/tasks", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateTask(
  id: number,
  input: Partial<TaskInput> & { clear_room?: boolean; is_active?: boolean },
) {
  return apiFetch<Task>(`/api/tasks/${id}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function deleteTask(id: number) {
  return apiFetch<void>(`/api/tasks/${id}`, { method: "DELETE" });
}

export function completeTask(id: number, source: "focus_session" | "direct") {
  return apiFetch<Task>(`/api/tasks/${id}/complete`, {
    method: "POST",
    body: JSON.stringify({ source }),
  });
}

export function snoozeTask(id: number, option: SnoozeOption) {
  return apiFetch<Task>(`/api/tasks/${id}/snooze`, {
    method: "POST",
    body: JSON.stringify({ option }),
  });
}

/* ---- Rooms ---- */

export type Room = {
  id: number;
  name: string;
  sort_order: number;
  ratio: number | null;
  band: Band | null;
  task_count: number;
  due_count: number;
};

export function getRooms() {
  return apiFetch<Room[]>("/api/rooms");
}

export function createRoom(name: string) {
  return apiFetch<Room>("/api/rooms", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export function updateRoom(id: number, input: { name?: string; sort_order?: number }) {
  return apiFetch<Room>(`/api/rooms/${id}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function deleteRoom(id: number) {
  return apiFetch<void>(`/api/rooms/${id}`, { method: "DELETE" });
}

/* ---- Focus & sessions ---- */

export type FocusResponse = {
  tasks: Task[];
  total_active_tasks: number;
};

export function getFocus(effort?: Effort) {
  const qs = effort ? `?effort=${effort}` : "";
  return apiFetch<FocusResponse>(`/api/focus${qs}`);
}

export type SessionResponse = {
  tasks: Task[];
  total_minutes: number;
};

export function buildSession(input: {
  minutes?: number;
  room_id?: number;
  effort?: Effort;
}) {
  return apiFetch<SessionResponse>("/api/sessions/build", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

/* ---- Settings ---- */

export type Settings = {
  daily_focus_count: number;
  default_session_minutes: number;
  daily_nudge_time: string; // "HH:MM", or "" when the nudge is off
  timezone: string;
};

export function getSettings() {
  return apiFetch<Settings>("/api/settings");
}

export function updateSettings(input: Partial<Settings>) {
  return apiFetch<Settings>("/api/settings", {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

/* ---- Onboarding ---- */

export type OnboardingRoomInput = { name: string; type: string };

export function runOnboarding(input: {
  rooms: OnboardingRoomInput[];
  has_pets: boolean;
  has_kids: boolean;
}) {
  return apiFetch<{ rooms_created: number; tasks_created: number }>(
    "/api/onboarding",
    { method: "POST", body: JSON.stringify(input) },
  );
}
