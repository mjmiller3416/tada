/**
 * Frontend vocabulary for supplies (SPEC §6, Phase 2) — same idea as
 * decay.ts: every surface uses the same warm labels and the same inline
 * "heads up" flag when a task's supplies are running low.
 */

import type { SupplyStatus, Task } from "./api";
import type { ChipTone } from "@/components/ui";

export const SUPPLY_STATUS_LABEL: Record<SupplyStatus, string> = {
  in_stock: "Stocked",
  low: "Running low",
  out: "All out",
};

export const SUPPLY_STATUS_TONE: Record<SupplyStatus, ChipTone> = {
  in_stock: "mint",
  low: "peach",
  out: "berry",
};

/**
 * The inline flag for a surfaced task (SPEC §6: "heads up — you're low
 * on floor cleaner"). Null when everything the task uses is stocked.
 */
export function supplyNote(task: Task): string | null {
  const low = task.supplies.filter((s) => s.status === "low").map((s) => s.name);
  const out = task.supplies.filter((s) => s.status === "out").map((s) => s.name);
  if (low.length === 0 && out.length === 0) return null;

  const parts: string[] = [];
  if (out.length > 0) parts.push(`out of ${listOf(out)}`);
  if (low.length > 0) parts.push(`low on ${listOf(low)}`);
  return `Heads up — you're ${parts.join(" and ")}`;
}

function listOf(names: string[]): string {
  const lowered = names.map((n) => n.toLowerCase());
  if (lowered.length === 1) return lowered[0];
  return `${lowered.slice(0, -1).join(", ")} and ${lowered[lowered.length - 1]}`;
}
