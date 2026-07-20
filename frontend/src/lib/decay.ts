/**
 * Frontend vocabulary for the decay engine (SPEC §4 + §5): every surface
 * maps the backend's `band` to the same warm, no-guilt language and the
 * same status tokens. Nothing here says "overdue" to her — urgency reads
 * as "this one could use some love", never as being behind.
 */

import type { Band, Effort } from "./api";
import type { ChipTone } from "@/components/ui";

/** The status token each band reads from (defined in globals.css). */
export const BAND_COLOR_VAR: Record<Band, string> = {
  fresh: "var(--status-fresh)",
  aging: "var(--status-aging)",
  due: "var(--status-due)",
  overdue: "var(--status-overdue)",
};

/** Warm labels — priority as a gradient, never a scold. */
export const BAND_LABEL: Record<Band, string> = {
  fresh: "Sparkling",
  aging: "Doing fine",
  due: "Ready for a clean",
  overdue: "Could use some love",
};

export const EFFORT_LABEL: Record<Effort, string> = {
  quick: "Quick win",
  deep: "Deep clean",
};

/** Cadence tier presets (SPEC §3). */
export const CADENCE_PRESETS: { label: string; days: number }[] = [
  { label: "Daily", days: 1 },
  { label: "Weekly", days: 7 },
  { label: "Monthly", days: 30 },
  { label: "Seasonal", days: 91 },
  { label: "Yearly", days: 365 },
];

export function cadenceLabel(days: number): string {
  const preset = CADENCE_PRESETS.find((p) => p.days === days);
  return preset ? preset.label : `Every ${days} days`;
}

/**
 * Deterministic cheerful tone per room so a room's chip is the same color
 * everywhere (cycles the bridge tints; never coral/teal, which mean
 * go/done).
 */
const ROOM_TONES: ChipTone[] = [
  "mint",
  "lavender",
  "peach",
  "periwinkle",
  "berry",
  "neutral",
];

export function roomTone(roomId: number | null): ChipTone {
  if (roomId == null) return "neutral";
  return ROOM_TONES[roomId % ROOM_TONES.length];
}

/** "Snoozed until" copy for planning views — quiet and factual. */
export function snoozedLabel(snoozedUntil: string): string {
  const until = new Date(snoozedUntil);
  const now = new Date();
  const sameDay = until.toDateString() === now.toDateString();
  const time = until.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  if (sameDay) return `resting until ${time}`;
  const day = until.toLocaleDateString([], { weekday: "short" });
  return `resting until ${day}`;
}
