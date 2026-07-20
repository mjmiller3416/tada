"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import AuthGate from "@/components/AuthGate";
import {
  createSupply,
  deleteSupply,
  getSupplies,
  updateSupply,
  type Supply,
  type SupplyStatus,
} from "@/lib/api";
import { SUPPLY_STATUS_LABEL, SUPPLY_STATUS_TONE } from "@/lib/supplies";
import { NAV_ITEMS } from "@/lib/nav";
import { AppShell, Button, Card, Chip } from "@/components/ui";
import styles from "./supplies.module.css";

const STATUSES: SupplyStatus[] = ["in_stock", "low", "out"];

/**
 * The supply inventory (SPEC §6, Phase 2): one tap to say where things
 * stand — in stock, running low, all out. Manual only, never guessed.
 * Anything low/out hops onto MealGenie's shopping list by itself; Tada
 * keeps no list of its own.
 */
export default function SuppliesPage() {
  return <AuthGate ownerOnly>{() => <SuppliesScreen />}</AuthGate>;
}

function SuppliesScreen() {
  const [supplies, setSupplies] = useState<Supply[] | null>(null);
  const [newName, setNewName] = useState("");
  const [adding, setAdding] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(() => {
    getSupplies()
      .then(setSupplies)
      .catch(() => setSupplies([]));
  }, []);

  useEffect(() => {
    load();
    return () => {
      if (toastTimer.current) clearTimeout(toastTimer.current);
    };
  }, [load]);

  function showToast(message: string) {
    setToast(message);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 2500);
  }

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    const name = newName.trim();
    if (!name || adding) return;
    setAdding(true);
    try {
      await createSupply(name);
      setNewName("");
      load();
    } finally {
      setAdding(false);
    }
  }

  async function handleStatus(supply: Supply, status: SupplyStatus) {
    if (supply.status === status) return;
    // Optimistic tap — the list re-sorts on reload.
    setSupplies(
      (current) =>
        current?.map((s) => (s.id === supply.id ? { ...s, status } : s)) ?? null,
    );
    try {
      const updated = await updateSupply(supply.id, { status });
      if (updated.pushed_to_shopping_list) {
        showToast(`${updated.name} added to your MealGenie list 🛒`);
      }
    } finally {
      load();
    }
  }

  async function handleRemove(supply: Supply) {
    if (!window.confirm(`Remove “${supply.name}” from your supplies?`)) return;
    try {
      await deleteSupply(supply.id);
    } finally {
      load();
    }
  }

  return (
    <AppShell title="Supplies" nav={NAV_ITEMS}>
      <p className={styles.help}>
        Tap where things stand. Anything low or out hops onto your MealGenie
        shopping list by itself. 🛒
      </p>

      <div className={styles.toast} aria-live="polite">
        {toast ?? " "}
      </div>

      <form onSubmit={handleAdd} className={styles.addRow}>
        <input
          type="text"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="e.g. Floor cleaner"
          className={styles.input}
          aria-label="New supply name"
        />
        <Button
          type="submit"
          variant="secondary"
          disabled={adding || newName.trim().length === 0}
        >
          Add
        </Button>
      </form>

      <div className={styles.list}>
        {supplies?.map((supply) => (
          <Card key={supply.id} className={styles.supplyCard}>
            <div className={styles.supplyTop}>
              <span className={styles.supplyName}>{supply.name}</span>
              <button
                type="button"
                className={styles.remove}
                onClick={() => handleRemove(supply)}
                aria-label={`Remove ${supply.name}`}
              >
                ✕
              </button>
            </div>
            <div className={styles.statusRow}>
              {STATUSES.map((status) => (
                <Chip
                  key={status}
                  tone={supply.status === status ? SUPPLY_STATUS_TONE[status] : "neutral"}
                  onClick={() => handleStatus(supply, status)}
                >
                  {SUPPLY_STATUS_LABEL[status]}
                </Chip>
              ))}
            </div>
            {supply.task_count > 0 && (
              <p className={styles.supplyMeta}>
                used by {supply.task_count} {supply.task_count === 1 ? "task" : "tasks"}
              </p>
            )}
          </Card>
        ))}

        {supplies !== null && supplies.length === 0 && (
          <Card padding="lg" className={styles.emptyCard}>
            <p className={styles.emptyText}>
              Nothing here yet — add the things you clean with, then link
              them to tasks so Tada can give you a heads-up before you run
              dry.
            </p>
          </Card>
        )}
      </div>
    </AppShell>
  );
}
