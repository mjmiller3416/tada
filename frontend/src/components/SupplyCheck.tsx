"use client";

import { useEffect, useRef, useState } from "react";
import { updateSupply, type SupplyBrief, type SupplyStatus } from "@/lib/api";
import { SUPPLY_STATUS_LABEL, SUPPLY_STATUS_TONE } from "@/lib/supplies";
import { Button, Chip } from "@/components/ui";
import styles from "./SupplyCheck.module.css";

const STATUSES: SupplyStatus[] = ["in_stock", "low", "out"];
const TOAST_MS = 3000;

type Toast = { text: string; tone: "ok" | "oops" };

type SupplyCheckProps = {
  /** The task's linked supplies, exactly as they ride along on the task. */
  supplies: SupplyBrief[];
  /**
   * Fired with the updated supply whenever a status changes — on the
   * optimistic tap, again when the server confirms, and once more to
   * roll back if it didn't. The parent patches its task state so the
   * chips (and the heads-up) repaint without a refetch.
   */
  onChanged: (supply: SupplyBrief) => void;
  onClose: () => void;
};

/**
 * The Supplies page's status chips, lifted onto a task card (SPEC §6
 * Supplies): one row per linked supply — Stocked / Running low / All out,
 * the current one filled — so noticing mid-task and recording it happen
 * in the same place. Owns the PATCH so the two surfaces that show it
 * (home focus cards, the session card) wire it identically.
 *
 * Status is still manual, never guessed; this only moves the tap to
 * where she is. Marking low/out still pushes to Enchanted Spoon's list
 * once per low-run — the backend dedupes, and the response tells us
 * which case we're in so the confirmation stays truthful.
 */
export default function SupplyCheck({ supplies, onChanged, onClose }: SupplyCheckProps) {
  const [toast, setToast] = useState<Toast | null>(null);
  const [changed, setChanged] = useState(false);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (toastTimer.current) clearTimeout(toastTimer.current);
    };
  }, []);

  function showToast(text: string, tone: Toast["tone"] = "ok") {
    setToast({ text, tone });
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), TOAST_MS);
  }

  async function handleTap(supply: SupplyBrief, status: SupplyStatus) {
    if (supply.status === status) return;
    // Optimistic — the chip repaints on the tap, like the Supplies page.
    onChanged({ ...supply, status });
    const name = supply.name.toLowerCase();
    try {
      const updated = await updateSupply(supply.id, { status });
      onChanged({ id: updated.id, name: updated.name, status: updated.status });
      setChanged(true);
      if (status === "in_stock") {
        showToast("Back in stock — noted.");
      } else if (updated.pushed_to_shopping_list) {
        showToast(`Got it — ${name} is on your Enchanted Spoon list 🛒`);
      } else if (updated.last_pushed_at) {
        showToast(`Got it — ${name}’s already on the list.`);
      } else {
        // Marked, but the list push didn't happen (Enchanted Spoon
        // unreachable) — say what did happen, nothing more.
        showToast(`Got it — ${name} is marked ${SUPPLY_STATUS_LABEL[status].toLowerCase()}.`);
      }
    } catch {
      onChanged(supply); // roll the chip back quietly
      showToast("That didn’t save — give it another tap in a sec.", "oops");
    }
  }

  return (
    <div className={styles.panel} role="group" aria-label="Supplies for this task">
      <p className={styles.hint}>
        Tap what’s running low — it goes straight onto the shopping list.
      </p>

      {supplies.map((supply) => (
        <div key={supply.id} className={styles.row}>
          <span className={styles.name}>{supply.name}</span>
          <div className={styles.chips}>
            {STATUSES.map((status) => (
              <Chip
                key={status}
                tone={supply.status === status ? SUPPLY_STATUS_TONE[status] : "neutral"}
                onClick={() => handleTap(supply, status)}
              >
                {SUPPLY_STATUS_LABEL[status]}
              </Chip>
            ))}
          </div>
        </div>
      ))}

      <p
        className={`${styles.toast} ${toast?.tone === "oops" ? styles.oops : ""}`}
        aria-live="polite"
      >
        {toast?.text}
      </p>

      <Button variant="ghost" onClick={onClose}>
        {changed ? "All set" : "Never mind"}
      </Button>
    </div>
  );
}
