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

/* ---- Write ordering ----
 * Completions and undos post fire-and-forget so Done and Undo never
 * hold up her flow (SPEC §5 — the celebration already happened). The
 * cost is a race: a surface that re-reads task state right after (the
 * home focus list, a session rebuild, Done Today) can fetch before the
 * write lands and then show stale truth until its next full reload.
 * So writers register their in-flight posts here and readers await
 * afterPendingWrites() before fetching — order restored without ever
 * blocking a tap. */

let pendingWrites: Promise<unknown>[] = [];

/** Register a fire-and-forget write so reads can order behind it.
 * Returns the original promise untouched. */
export function trackWrite<T>(promise: Promise<T>): Promise<T> {
  const entry = promise.then(
    () => undefined,
    () => undefined, // a failed write is settled too — never wedge reads
  );
  pendingWrites.push(entry);
  entry.then(() => {
    pendingWrites = pendingWrites.filter((p) => p !== entry);
  });
  return promise;
}

/** Resolves once every tracked write has settled — looping, so a write
 * that chains mid-wait (an undo behind its completion post) is caught
 * by the next pass rather than slipping through. */
export async function afterPendingWrites(): Promise<void> {
  while (pendingWrites.length > 0) {
    await Promise.allSettled([...pendingWrites]);
  }
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

/** The SPEC §4 color bands, plus "waiting" (Phase 11): a zone mission
 * outside its zone's week shows no color anywhere — a quiet fact, not a
 * nag — and shows its real band only during its active window. */
export type Band = "fresh" | "aging" | "due" | "overdue" | "waiting";
export type Effort = "quick" | "deep";
/** The form's two-way toggle. It maps onto task_type on the backend —
 * "maintenance" is the maintenance lane, "cleaning" is everything else.
 * The five-type editor arrives with Phase 11's review UI. */
export type Category = "cleaning" | "maintenance";
/** Which clock schedules a task (SPEC §4 lanes, Phase 10): decay for
 * routine / weekly_blessing / maintenance, the zone calendar for zone
 * missions, and her explicit choice for projects. Read-only until the
 * Phase 11 review UI. */
export type TaskType =
  | "routine"
  | "weekly_blessing"
  | "zone"
  | "maintenance"
  | "project";
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
  task_type: TaskType;
  cadence_days: number;
  estimated_minutes: number;
  effort: Effort;
  guest_facing: boolean;
  /** "Usually a Saturday job" (Phase 8): Monday = 0 … Sunday = 6, null =
   * no preference. A ranking boost on that day (and the day after) —
   * never a deadline. */
  preferred_day: number | null;
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
  /** The zone whose week governs this mission (lanes on, zone tasks
   * only): the home card's "This week's Kitchen mission" label and the
   * "waits for Kitchen week" copy both read it. Null otherwise. */
  zone_name: string | null;
};

export type TaskInput = {
  name: string;
  room_id: number | null;
  category?: Category;
  /** The Phase 11 five-type picker; wins over `category` when both are sent. */
  task_type?: TaskType;
  cadence_days: number;
  estimated_minutes: number;
  effort: Effort;
  assignee_id?: number | null;
  claimable?: boolean;
  supply_ids?: number[];
  notes?: string | null;
  preferred_day?: number | null;
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
    /** "When was this last done?" — a correction to history (Phase 4.6).
     * Never writes a CompletionLog; the decay curve simply re-anchors. */
    last_done_at?: string;
    clear_last_done?: boolean;
    /** Back to "no set day" (Phase 8); same pattern as clear_room. */
    clear_preferred_day?: boolean;
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

export type CompleteResponse = Task & {
  /** The CompletionLog row this completion wrote — the handle the Undo
   * toast needs (Phase 9). */
  completion_id: number;
};

export function completeTask(id: number, source: CompletionSource) {
  return apiFetch<CompleteResponse>(`/api/tasks/${id}/complete`, {
    method: "POST",
    body: JSON.stringify({ source }),
  });
}

/** Undo one of today's completions (Phase 9): decay state only — the
 * task returns to exactly the priority it had. Streaks and badges are
 * deliberately untouched; they only ever go up. */
export function undoCompletion(completionId: number) {
  return apiFetch<Task>(`/api/completions/${completionId}/undo`, {
    method: "POST",
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
  /** Phase 11: a mission-only zone session. Ignored while the lanes are
   * off — the backend gracefully falls back to the legacy zone session. */
  zone_missions?: boolean;
  /** Timer-extend top-up (Phase 5): skip what's already in the queue. */
  exclude_task_ids?: number[];
}) {
  return apiFetch<SessionResponse>("/api/sessions/build", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

/* ---- Rewards & Done Today (Phase 5) ---- */

export type Badge = {
  id: number;
  code: string;
  name: string;
  description: string;
  emoji: string;
  earned_at: string;
};

/** The session-complete badge check (SPEC §5's celebration + badge
 * check). `started_at` scopes new_badges to this session, including
 * badges earned mid-session on individual completions. */
export function completeSession(input: {
  tasks_done: number;
  started_at: string;
}) {
  return apiFetch<{ new_badges: Badge[] }>("/api/sessions/complete", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export type SessionTimer = {
  id: number;
  fires_at: string;
};

/** The optional "nudge me when time's up" timer — a real push through
 * the Reminder + cron plumbing, so it survives a pocketed phone. */
export function startSessionTimer(minutes: number) {
  return apiFetch<SessionTimer>("/api/sessions/timer", {
    method: "POST",
    body: JSON.stringify({ minutes }),
  });
}

export function extendSessionTimer(id: number, minutes: number) {
  return apiFetch<SessionTimer>(`/api/sessions/timer/${id}/extend`, {
    method: "POST",
    body: JSON.stringify({ minutes }),
  });
}

export function cancelSessionTimer(id: number) {
  return apiFetch<void>(`/api/sessions/timer/${id}`, { method: "DELETE" });
}

export type DoneTodayEntry = {
  id: number;
  task_name: string;
  room_id: number | null;
  room_name: string | null;
  completed_at: string;
  completed_by_id: number;
  completed_by_name: string;
  source: CompletionSource;
};

export type DoneTodayResponse = {
  date: string;
  completions: DoneTodayEntry[];
  streak: number;
  badges: Badge[];
  household_members: number;
};

export function getDoneToday() {
  return apiFetch<DoneTodayResponse>("/api/done-today");
}

/* ---- Settings ---- */

export type Settings = {
  daily_focus_count: number;
  default_session_minutes: number;
  daily_nudge_time: string; // "HH:MM", or "" when the nudge is off
  timezone: string;
  zones_enabled: boolean; // Phase 3 overlays — opt-in, off by default
  campaigns_enabled: boolean;
  // Vacation mode (Phase 4.6): last paused day "YYYY-MM-DD", "" = home.
  // Pauses the nudges only — decay keeps running honestly throughout.
  vacation_until: string;
  // Phase 11: the scheduling-lanes flag (flip on after the
  // reclassification review) and Zone 3's rotating second room (a room
  // id as a string, "" = none this rotation).
  zone_lane_enabled: boolean;
  zone_3_extra_room_id: string;
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

export function createMember(input: {
  name: string;
  pin: string;
  role?: "kid" | "owner"; // defaults to "kid"; "owner" = a second adult (Phase 4.6)
}) {
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

/* ---- Lists (Phase 6, grown from Phase 4 packing — its own module,
   apart from cleaning; list items never touch the focus surfaces) ---- */

export type ListKind = "packing" | "shopping" | "tasks" | "custom";

export type ListSummary = {
  id: number;
  name: string;
  kind: ListKind;
  is_template: boolean;
  event_date: string | null; // ISO date
  destination: string | null;
  duration: string | null; // free text ("5 days", "a long weekend")
  status: "active" | "archived";
  packed_count: number;
  total_count: number;
  percent: number;
  /** Computed price totals — decimal strings ("340.00"), null until at
   * least one item on the list has a price. Checked reads as
   * spend-to-date on a shopping list. */
  checked_price: string | null;
  total_price: string | null;
  created_at: string;
};

export type ListItem = {
  id: number;
  name: string;
  quantity: string | null;
  notes: string | null;
  packed: boolean;
  price: string | null; // decimal string ("40.00"), never a float
  sort_order: number;
};

export type ListSection = {
  id: number;
  name: string;
  sort_order: number;
  packed_count: number;
  total_count: number;
  items: ListItem[];
};

export type ListDetail = ListSummary & {
  reminder_enabled: boolean;
  sections: ListSection[];
};

export function getListTemplates() {
  return apiFetch<ListSummary[]>("/api/lists/templates");
}

export function getLists() {
  return apiFetch<ListSummary[]>("/api/lists");
}

/** Clones a source list (a template, or an archived list to reuse). */
export function createList(input: {
  source_list_id: number;
  name?: string;
  event_date?: string | null;
  destination?: string;
  duration?: string;
}) {
  return apiFetch<ListDetail>("/api/lists", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getList(id: number) {
  return apiFetch<ListDetail>(`/api/lists/${id}`);
}

export function updateList(
  id: number,
  input: {
    name?: string;
    event_date?: string;
    clear_event_date?: boolean;
    destination?: string;
    clear_destination?: boolean;
    duration?: string;
    clear_duration?: boolean;
    status?: "active" | "archived";
    reminder_enabled?: boolean;
    reminder_days_before?: number;
  },
) {
  return apiFetch<ListDetail>(`/api/lists/${id}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function deleteList(id: number) {
  return apiFetch<void>(`/api/lists/${id}`, { method: "DELETE" });
}

export function addListSection(listId: number, name: string) {
  return apiFetch<ListDetail>(`/api/lists/${listId}/sections`, {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export function updateListSection(
  id: number,
  input: { name?: string; sort_order?: number },
) {
  return apiFetch<ListDetail>(`/api/lists/sections/${id}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function deleteListSection(id: number) {
  return apiFetch<ListDetail>(`/api/lists/sections/${id}`, {
    method: "DELETE",
  });
}

export function addListItem(
  sectionId: number,
  input: { name: string; quantity?: string; notes?: string; price?: string },
) {
  return apiFetch<ListDetail>(`/api/lists/sections/${sectionId}/items`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateListItem(
  id: number,
  input: {
    name?: string;
    quantity?: string;
    clear_quantity?: boolean;
    notes?: string;
    clear_notes?: boolean;
    packed?: boolean;
    price?: string; // decimal string, e.g. "12.50"
    clear_price?: boolean;
    sort_order?: number;
  },
) {
  return apiFetch<ListDetail>(`/api/lists/items/${id}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function deleteListItem(id: number) {
  return apiFetch<ListDetail>(`/api/lists/items/${id}`, {
    method: "DELETE",
  });
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
