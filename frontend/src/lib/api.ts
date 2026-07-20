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
export type Category = "cleaning" | "maintenance";
export type SnoozeOption = "later_today" | "tomorrow" | "few_days" | "wake";
export type SupplyStatus = "in_stock" | "low" | "out";

export type SupplyBrief = {
  id: number;
  name: string;
  status: SupplyStatus;
};

export type Task = {
  id: number;
  name: string;
  room_id: number | null;
  room_name: string | null;
  category: Category;
  cadence_days: number;
  estimated_minutes: number;
  effort: Effort;
  guest_facing: boolean;
  last_done_at: string | null;
  snoozed_until: string | null;
  is_snoozed: boolean;
  is_active: boolean;
  assignee_id: number | null;
  assignee_name: string | null;
  claimable: boolean;
  supplies: SupplyBrief[];
  notes: string | null;
  ratio: number;
  band: Band;
};

export type TaskInput = {
  name: string;
  room_id: number | null;
  category?: Category;
  cadence_days: number;
  estimated_minutes: number;
  effort: Effort;
  assignee_id?: number | null;
  claimable?: boolean;
  supply_ids?: number[];
  notes?: string | null;
};

export function getTasks(params?: {
  room_id?: number;
  effort?: Effort;
  category?: Category;
  include_inactive?: boolean;
}) {
  const query = new URLSearchParams();
  if (params?.room_id != null) query.set("room_id", String(params.room_id));
  if (params?.effort) query.set("effort", params.effort);
  if (params?.category) query.set("category", params.category);
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
  input: Partial<TaskInput> & {
    clear_room?: boolean;
    clear_assignee?: boolean;
    is_active?: boolean;
  },
) {
  return apiFetch<Task>(`/api/tasks/${id}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function claimTask(id: number) {
  return apiFetch<Task>(`/api/tasks/${id}/claim`, { method: "POST" });
}

export function deleteTask(id: number) {
  return apiFetch<void>(`/api/tasks/${id}`, { method: "DELETE" });
}

export type CompletionSource =
  | "focus_session"
  | "direct"
  | "guest_mode"
  | "zone"
  | "campaign";

export function completeTask(id: number, source: CompletionSource) {
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
  zone_id: number | null;
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

export function updateRoom(
  id: number,
  input: { name?: string; sort_order?: number; zone_id?: number; clear_zone?: boolean },
) {
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
  zone_id?: number;
  campaign_id?: number;
  guest?: boolean;
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
  zones_enabled: boolean; // Phase 3 overlays — opt-in, off by default
  campaigns_enabled: boolean;
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

/* ---- Chores (Phase 2, the kid surface) ---- */

export type ChoresResponse = {
  mine: Task[];
  up_for_grabs: Task[];
};

export function getChores() {
  return apiFetch<ChoresResponse>("/api/chores");
}

/* ---- Household members (Phase 2) ---- */

export type Member = {
  id: number;
  name: string;
  role: "owner" | "kid";
  assigned_count: number;
};

export function getMembers() {
  return apiFetch<Member[]>("/api/members");
}

export function createMember(input: { name: string; pin: string }) {
  return apiFetch<Member>("/api/members", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateMember(id: number, input: { name?: string; pin?: string }) {
  return apiFetch<Member>(`/api/members/${id}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function deleteMember(id: number) {
  return apiFetch<void>(`/api/members/${id}`, { method: "DELETE" });
}

/* ---- Supplies (Phase 2) ---- */

export type Supply = {
  id: number;
  name: string;
  status: SupplyStatus;
  last_pushed_at: string | null;
  task_count: number;
  pushed_to_shopping_list: boolean;
};

export function getSupplies() {
  return apiFetch<Supply[]>("/api/supplies");
}

export function createSupply(name: string) {
  return apiFetch<Supply>("/api/supplies", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export function updateSupply(
  id: number,
  input: { name?: string; status?: SupplyStatus },
) {
  return apiFetch<Supply>(`/api/supplies/${id}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function deleteSupply(id: number) {
  return apiFetch<void>(`/api/supplies/${id}`, { method: "DELETE" });
}

/* ---- Zones (Phase 3, the FlyLady overlay) ---- */

export type ZoneRoomBrief = { id: number; name: string };

export type Zone = {
  id: number;
  name: string;
  week_of_month: number;
  rooms: ZoneRoomBrief[];
};

export type ZonesResponse = {
  zones: Zone[];
  week_of_month: number;
  current_zone_id: number | null;
};

export function getZones() {
  return apiFetch<ZonesResponse>("/api/zones");
}

/** Seeds FlyLady's five zones + auto-maps rooms; safe to call again. */
export function setupZones() {
  return apiFetch<ZonesResponse>("/api/zones/setup", { method: "POST" });
}

export function updateZone(id: number, input: { name: string }) {
  return apiFetch<ZonesResponse>(`/api/zones/${id}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

/* ---- Campaigns (Phase 3, seasonal overlays) ---- */

export type Campaign = {
  id: number;
  name: string;
  season: string | null;
  start_date: string; // ISO date
  end_date: string;
  active: boolean;
  is_running: boolean;
  total_tasks: number;
  done_tasks: number;
  percent: number;
};

export type CampaignTaskEntry = { task: Task; done: boolean };

export type CampaignDetail = Campaign & { tasks: CampaignTaskEntry[] };

export function getCampaigns() {
  return apiFetch<Campaign[]>("/api/campaigns");
}

export function getCampaign(id: number) {
  return apiFetch<CampaignDetail>(`/api/campaigns/${id}`);
}

export function createCampaign(input: {
  name: string;
  season?: string;
  start_date: string;
  end_date: string;
  task_ids: number[];
}) {
  return apiFetch<CampaignDetail>("/api/campaigns", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateCampaign(
  id: number,
  input: {
    name?: string;
    season?: string;
    start_date?: string;
    end_date?: string;
    active?: boolean;
    task_ids?: number[];
  },
) {
  return apiFetch<CampaignDetail>(`/api/campaigns/${id}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function deleteCampaign(id: number) {
  return apiFetch<void>(`/api/campaigns/${id}`, { method: "DELETE" });
}

/* ---- Onboarding ---- */

export type OnboardingRoomInput = { name: string; type: string };

export function runOnboarding(input: {
  rooms: OnboardingRoomInput[];
  has_pets: boolean;
  has_kids: boolean;
  enable_zones?: boolean;
}) {
  return apiFetch<{ rooms_created: number; tasks_created: number }>(
    "/api/onboarding",
    { method: "POST", body: JSON.stringify(input) },
  );
}
