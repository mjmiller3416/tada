import type { ChipTone } from "@/components/ui";
import type { ListKind } from "@/lib/api";

/**
 * Display metadata for the four list kinds (Phase 6). Kind drives small
 * presentation differences only — packing leans on sections, shopping
 * makes price prominent, tasks reads flat, custom has no opinion. Tones
 * reuse the chip tints so lists look native next to the cleaning
 * surfaces.
 */
export const LIST_KIND_META: Record<
  ListKind,
  { label: string; emoji: string; tone: ChipTone }
> = {
  packing: { label: "Packing", emoji: "🧳", tone: "periwinkle" },
  shopping: { label: "Shopping", emoji: "🛒", tone: "mint" },
  tasks: { label: "To-do", emoji: "✅", tone: "peach" },
  custom: { label: "Custom", emoji: "✨", tone: "lavender" },
};

/**
 * Display-only emoji for the seeded starter templates, so the template
 * picker stays friendly and scannable now that identity lives in the
 * name (the old 10-way category is gone). Falls back to the kind emoji
 * for anything renamed or unknown — nothing breaks, it just gets the
 * generic icon.
 */
const TEMPLATE_EMOJI: Record<string, string> = {
  Moving: "📦",
  Travel: "🧳",
  Events: "🎉",
  Work: "💼",
  "Outdoor Activities": "🏕️",
  "Family and Kids": "🧸",
  "Emergency Preparedness": "🚨",
  "Shipping and Storage": "📮",
  "Everyday Bags and Kits": "👜",
  Custom: "✨",
  "School Supplies": "🎒",
  "Christmas Gifts": "🎄",
  Birthday: "🎂",
};

export function templateEmoji(name: string, kind: ListKind): string {
  return TEMPLATE_EMOJI[name] ?? LIST_KIND_META[kind].emoji;
}

/**
 * The verb for a checked item, by kind: on a shopping list checked
 * means bought, on a packing list it means packed.
 */
export function checkedVerb(kind: ListKind): string {
  if (kind === "packing") return "packed";
  if (kind === "shopping") return "bought";
  if (kind === "tasks") return "done";
  return "checked off";
}

/**
 * "$340" / "$12.50" from a decimal string ("340.00"). Whole-dollar
 * amounts drop the cents so totals read like she'd say them.
 */
export function formatMoney(decimal: string): string {
  const [dollars, cents] = decimal.split(".");
  return cents === "00" || cents === undefined
    ? `$${dollars}`
    : `$${dollars}.${cents}`;
}

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
