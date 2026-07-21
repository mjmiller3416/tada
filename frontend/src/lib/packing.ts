import type { ChipTone } from "@/components/ui";
import type { PackingCategory } from "@/lib/api";

/**
 * Display metadata for the ten packing categories (Phase 4). Emoji keep
 * the template picker friendly and scannable; tones reuse the chip
 * tints so packing looks native next to the cleaning surfaces.
 */
export const PACKING_CATEGORY_META: Record<
  PackingCategory,
  { label: string; emoji: string; tone: ChipTone }
> = {
  moving: { label: "Moving", emoji: "📦", tone: "peach" },
  travel: { label: "Travel", emoji: "🧳", tone: "periwinkle" },
  events: { label: "Events", emoji: "🎉", tone: "berry" },
  work: { label: "Work", emoji: "💼", tone: "neutral" },
  outdoor: { label: "Outdoor", emoji: "🏕️", tone: "mint" },
  family_kids: { label: "Family & kids", emoji: "🧸", tone: "lavender" },
  emergency: { label: "Emergency", emoji: "🚨", tone: "coral" },
  shipping_storage: { label: "Shipping & storage", emoji: "📮", tone: "neutral" },
  everyday: { label: "Everyday bags", emoji: "👜", tone: "peach" },
  custom: { label: "Custom", emoji: "✨", tone: "lavender" },
};

/** "Jul 24" — short friendly date from an ISO date string. */
export function prettyEventDate(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString([], {
    month: "short",
    day: "numeric",
  });
}

/**
 * A warm countdown phrase for an event date, or null once it's passed
 * (no guilt — a done trip just shows its date).
 */
export function countdownLabel(iso: string): string | null {
  const event = new Date(`${iso}T00:00:00`);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const days = Math.round((event.getTime() - today.getTime()) / 86400000);
  if (days < 0) return null;
  if (days === 0) return "today!";
  if (days === 1) return "tomorrow";
  return `in ${days} days`;
}
