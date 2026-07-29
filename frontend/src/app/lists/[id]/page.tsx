"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import AuthGate from "@/components/AuthGate";
import {
  addListItem,
  addListSection,
  deleteList,
  deleteListItem,
  deleteListSection,
  getList,
  updateList,
  updateListItem,
  updateListSection,
  type ListDetail,
  type ListSection,
} from "@/lib/api";
import { NAV_ITEMS } from "@/lib/nav";
import {
  checkedVerb,
  countdownLabel,
  formatMoney,
  LIST_KIND_META,
  prettyEventDate,
} from "@/lib/lists";
import { AppShell, Button, Card, Chip, Confetti } from "@/components/ui";
import styles from "./list-detail.module.css";

/**
 * One list as a FULL grouped checklist (Phase 6, grown from Phase 4
 * packing) — deliberately NOT the one-task-at-a-time focus flow. Lists
 * are the place seeing everything wins: sections as sticky headers,
 * checkboxes beneath, progress up top, and a little confetti when the
 * last item is checked.
 *
 * Sections collapse (Phase 6): state lives in localStorage keyed per
 * list — a per-device view preference, deliberately NOT synced, so her
 * phone can be collapsed mid-pack while the Chromebook stays expanded.
 * A section auto-collapses when it *reaches* 100% — on the transition
 * only, never on load — so a big list visibly shrinks as she works.
 */
export default function ListPage() {
  return <AuthGate ownerOnly>{() => <ListScreen />}</AuthGate>;
}

function ListScreen() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const listId = Number(params.id);

  const [detail, setDetail] = useState<ListDetail | null>(null);
  const [missing, setMissing] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [celebrating, setCelebrating] = useState(false);

  // ---- Small inline forms ----
  const [renaming, setRenaming] = useState(false);
  const [newName, setNewName] = useState("");
  const [newItemBySection, setNewItemBySection] = useState<Record<number, string>>({});
  const [newSection, setNewSection] = useState("");
  const [renamingSectionId, setRenamingSectionId] = useState<number | null>(null);
  const [sectionName, setSectionName] = useState("");

  // Destination/duration are typed freely, so they're drafts committed
  // on blur — unlike the date input, which saves on change.
  const [destinationDraft, setDestinationDraft] = useState("");
  const [durationDraft, setDurationDraft] = useState("");

  /* Celebrate only on the transition into 100%, not on page load. */
  const prevPercent = useRef<number | null>(null);
  /* Per-section packed counts from the previous state — the "on the
     transition only" guard for auto-collapse. */
  const prevSectionPacked = useRef<Map<number, number>>(new Map());

  // ---- Collapse state: per-device, per-list (localStorage, not DB) ----
  const storageKey = `tada:list-collapsed:${listId}`;
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());

  const persistCollapsed = useCallback(
    (next: Set<number>) => {
      try {
        localStorage.setItem(storageKey, JSON.stringify([...next]));
      } catch {
        // Storage full or blocked — collapse still works for this visit.
      }
    },
    [storageKey],
  );

  useEffect(() => {
    try {
      const raw = localStorage.getItem(storageKey);
      if (raw) setCollapsed(new Set(JSON.parse(raw) as number[]));
    } catch {
      // Unreadable state is no state.
    }
  }, [storageKey]);

  function toggleSection(sectionId: number) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(sectionId)) next.delete(sectionId);
      else next.add(sectionId);
      persistCollapsed(next);
      return next;
    });
  }

  function setAllCollapsed(sections: ListSection[], value: boolean) {
    const next = value ? new Set(sections.map((s) => s.id)) : new Set<number>();
    persistCollapsed(next);
    setCollapsed(next);
  }

  useEffect(() => {
    getList(listId)
      .then((d) => {
        prevPercent.current = d.percent;
        prevSectionPacked.current = new Map(
          d.sections.map((s) => [s.id, s.packed_count]),
        );
        setDetail(d);
        setDestinationDraft(d.destination ?? "");
        setDurationDraft(d.duration ?? "");
      })
      .catch(() => setMissing(true));
  }, [listId]);

  /** Every mutation returns the canonical full list — one setter for all. */
  function apply(next: ListDetail) {
    if (
      prevPercent.current !== null &&
      prevPercent.current < 100 &&
      next.percent === 100 &&
      next.total_count > 0
    ) {
      setCelebrating(true);
    }
    prevPercent.current = next.percent;

    // Auto-collapse any section that just reached 100% — transition
    // only (the ref holds the previous state), and only when there's
    // more than one section to shrink away.
    if (next.sections.length > 1) {
      const justFinished = next.sections
        .filter((section) => {
          const prev = prevSectionPacked.current.get(section.id);
          return (
            section.total_count > 0 &&
            section.packed_count === section.total_count &&
            prev !== undefined &&
            prev < section.total_count
          );
        })
        .map((section) => section.id);
      if (justFinished.length > 0) {
        setCollapsed((prev) => {
          const merged = new Set(prev);
          justFinished.forEach((id) => merged.add(id));
          persistCollapsed(merged);
          return merged;
        });
      }
    }
    prevSectionPacked.current = new Map(
      next.sections.map((s) => [s.id, s.packed_count]),
    );

    setDetail(next);
  }

  async function togglePacked(itemId: number, packed: boolean) {
    if (!detail) return;
    // Optimistic flip so the checkbox feels instant; reconcile after.
    setDetail({
      ...detail,
      sections: detail.sections.map((section) => ({
        ...section,
        items: section.items.map((item) =>
          item.id === itemId ? { ...item, packed } : item,
        ),
      })),
    });
    try {
      apply(await updateListItem(itemId, { packed }));
    } catch {
      apply(await getList(listId).catch(() => detail));
    }
  }

  async function commitPrice(itemId: number, raw: string, current: string | null) {
    if (!detail) return;
    const trimmed = raw.trim();
    if (trimmed === "") {
      if (current === null) return;
      apply(await updateListItem(itemId, { clear_price: true }).catch(() => detail));
      return;
    }
    const value = Number(trimmed);
    if (!Number.isFinite(value) || value < 0) return;
    const normalized = value.toFixed(2);
    if (normalized === current) return;
    apply(await updateListItem(itemId, { price: normalized }).catch(() => detail));
  }

  async function handleAddItem(section: ListSection) {
    const name = (newItemBySection[section.id] ?? "").trim();
    if (!name || !detail) return;
    setNewItemBySection((m) => ({ ...m, [section.id]: "" }));
    apply(await addListItem(section.id, { name }).catch(() => detail));
  }

  async function handleAddSection() {
    const name = newSection.trim();
    if (!name || !detail) return;
    setNewSection("");
    apply(await addListSection(listId, name).catch(() => detail));
  }

  async function handleRename() {
    if (!detail || !newName.trim()) return;
    setRenaming(false);
    apply(await updateList(listId, { name: newName.trim() }).catch(() => detail));
  }

  async function handleRenameSection(sectionId: number) {
    if (!detail || !sectionName.trim()) return;
    setRenamingSectionId(null);
    apply(
      await updateListSection(sectionId, { name: sectionName.trim() }).catch(
        () => detail,
      ),
    );
  }

  async function handleDeleteItem(itemId: number) {
    if (!detail) return;
    apply(await deleteListItem(itemId).catch(() => detail));
  }

  async function handleDeleteSection(section: ListSection) {
    if (!detail) return;
    if (
      section.items.length > 0 &&
      !window.confirm(`Remove “${section.name}” and its ${section.items.length} items?`)
    )
      return;
    apply(await deleteListSection(section.id).catch(() => detail));
  }

  async function moveItem(itemId: number, from: number, to: number) {
    if (!detail || to < 0) return;
    void from;
    apply(await updateListItem(itemId, { sort_order: to }).catch(() => detail));
  }

  async function moveSection(sectionId: number, to: number) {
    if (!detail || to < 0) return;
    apply(await updateListSection(sectionId, { sort_order: to }).catch(() => detail));
  }

  async function handleEventDate(value: string) {
    if (!detail) return;
    apply(
      await updateList(
        listId,
        value ? { event_date: value } : { clear_event_date: true },
      ).catch(() => detail),
    );
  }

  async function commitDestination() {
    if (!detail) return;
    const value = destinationDraft.trim();
    if (value === (detail.destination ?? "")) return;
    const next = await updateList(
      listId,
      value ? { destination: value } : { clear_destination: true },
    ).catch(() => detail);
    apply(next);
    setDestinationDraft(next.destination ?? "");
  }

  async function commitDuration() {
    if (!detail) return;
    const value = durationDraft.trim();
    if (value === (detail.duration ?? "")) return;
    const next = await updateList(
      listId,
      value ? { duration: value } : { clear_duration: true },
    ).catch(() => detail);
    apply(next);
    setDurationDraft(next.duration ?? "");
  }

  async function toggleReminder() {
    if (!detail) return;
    apply(
      await updateList(listId, {
        reminder_enabled: !detail.reminder_enabled,
      }).catch(() => detail),
    );
  }

  async function toggleArchive() {
    if (!detail) return;
    const next = detail.status === "active" ? "archived" : "active";
    apply(await updateList(listId, { status: next }).catch(() => detail));
    if (next === "archived") router.push("/lists");
  }

  async function handleDeleteList() {
    if (!detail) return;
    // Name the stakes: she has hand-entered lists past 100 items, and an
    // accidental delete would be genuinely costly.
    const count = detail.total_count;
    const message =
      count > 0
        ? `Delete “${detail.name}” and its ${count} ${count === 1 ? "item" : "items"}? This can't be undone — archiving keeps it around instead.`
        : `Delete “${detail.name}”? This can't be undone — archiving keeps it around instead.`;
    if (!window.confirm(message)) return;
    try {
      await deleteList(listId);
      router.push("/lists");
    } catch {
      // Nothing was deleted — stay on the list.
    }
  }

  if (missing) {
    return (
      <AppShell title="Lists" nav={NAV_ITEMS}>
        <Card padding="lg">
          <p className={styles.emptyText}>
            Hmm, that list isn&apos;t here anymore.
          </p>
          <Button variant="secondary" fullWidth onClick={() => router.push("/lists")}>
            Back to lists
          </Button>
        </Card>
      </AppShell>
    );
  }

  if (!detail) {
    return <AppShell title="Lists" nav={NAV_ITEMS}>{null}</AppShell>;
  }

  const meta = LIST_KIND_META[detail.kind];
  const verb = checkedVerb(detail.kind);
  const countdown = detail.event_date ? countdownLabel(detail.event_date) : null;
  const remaining = detail.total_count - detail.packed_count;
  /* One section = a plain flat list: no group header, no group bar —
     the structure is still there underneath, it just stays quiet. */
  const singleSection = detail.sections.length === 1;
  const allCollapsed =
    detail.sections.length > 0 &&
    detail.sections.every((section) => collapsed.has(section.id));

  return (
    <AppShell nav={NAV_ITEMS}>
      <Confetti active={celebrating} onComplete={() => setCelebrating(false)} />

      <button
        type="button"
        className={styles.back}
        onClick={() => router.push("/lists")}
      >
        ← All lists
      </button>

      <header className={styles.header}>
        {renaming ? (
          <div className={styles.renameRow}>
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleRename()}
              className={styles.input}
              autoFocus
            />
            <Button variant="secondary" onClick={handleRename}>
              Save
            </Button>
          </div>
        ) : (
          <h1 className={styles.title}>{detail.name}</h1>
        )}
        <div className={styles.headerChips}>
          <Chip tone={meta.tone}>
            {meta.emoji} {meta.label}
          </Chip>
          {detail.status === "archived" && <Chip tone="neutral">Archived</Chip>}
        </div>
      </header>

      <Card className={styles.summaryCard}>
        <div
          className={styles.progressTrack}
          role="progressbar"
          aria-valuenow={detail.percent}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div
            className={styles.progressFill}
            style={{ width: `${detail.percent}%` }}
          />
        </div>
        <p className={styles.progressText}>
          {detail.percent === 100 && detail.total_count > 0
            ? `All ${verb} — you're all set! 🎉`
            : `${detail.packed_count} of ${detail.total_count} ${verb}` +
              (remaining > 0 ? ` · ${remaining} to go` : "")}
        </p>
        {detail.total_price !== null && detail.checked_price !== null && (
          <p className={styles.totals}>
            💵 {formatMoney(detail.checked_price)} of{" "}
            {formatMoney(detail.total_price)}
          </p>
        )}

        <div className={styles.eventRow}>
          <label className={styles.eventLabel}>
            <span className={styles.label}>
              {detail.kind === "packing" ? "Event date" : "Date (optional)"}
            </span>
            <input
              type="date"
              value={detail.event_date ?? ""}
              onChange={(e) => handleEventDate(e.target.value)}
              className={styles.input}
            />
          </label>
          {detail.event_date && countdown && (
            <span className={styles.countdown}>{countdown}</span>
          )}
        </div>
        {detail.kind === "packing" && (
          <div className={styles.eventRow}>
            <label className={styles.eventLabel}>
              <span className={styles.label}>Destination</span>
              <input
                type="text"
                value={destinationDraft}
                onChange={(e) => setDestinationDraft(e.target.value)}
                onBlur={commitDestination}
                onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
                placeholder="Where to?"
                className={styles.input}
              />
            </label>
            <label className={styles.eventLabel}>
              <span className={styles.label}>How long?</span>
              <input
                type="text"
                value={durationDraft}
                onChange={(e) => setDurationDraft(e.target.value)}
                onBlur={commitDuration}
                onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
                placeholder="e.g. 5 days"
                className={styles.input}
              />
            </label>
          </div>
        )}
        {detail.event_date && (
          <Chip
            tone={detail.reminder_enabled ? "mint" : "neutral"}
            onClick={toggleReminder}
          >
            {detail.reminder_enabled
              ? "Countdown reminder on ✓"
              : "Remind me as it gets close"}
          </Chip>
        )}
      </Card>

      <div className={styles.toolbar}>
        <Chip tone={editMode ? "coral" : "neutral"} onClick={() => setEditMode((v) => !v)}>
          {editMode ? "Done editing" : "Edit list"}
        </Chip>
        {!singleSection && detail.sections.length > 0 && (
          <Chip
            tone="neutral"
            onClick={() => setAllCollapsed(detail.sections, !allCollapsed)}
          >
            {allCollapsed ? "Expand all" : "Collapse all"}
          </Chip>
        )}
        {editMode && (
          <>
            <Chip
              tone="neutral"
              onClick={() => {
                setNewName(detail.name);
                setRenaming(true);
              }}
            >
              Rename
            </Chip>
            <Chip tone="neutral" onClick={toggleArchive}>
              {detail.status === "active" ? "Archive" : "Restore"}
            </Chip>
          </>
        )}
      </div>

      <div className={styles.sections}>
        {detail.sections.map((section, sectionIndex) => {
          const isCollapsed = !singleSection && collapsed.has(section.id);
          const showHeader = !singleSection || editMode;
          return (
            <section key={section.id} className={styles.section}>
              {showHeader && (
                <div className={styles.sectionHeader}>
                  {renamingSectionId === section.id ? (
                    <div className={styles.renameRow}>
                      <input
                        type="text"
                        value={sectionName}
                        onChange={(e) => setSectionName(e.target.value)}
                        onKeyDown={(e) =>
                          e.key === "Enter" && handleRenameSection(section.id)
                        }
                        className={styles.input}
                        autoFocus
                      />
                      <Button
                        variant="secondary"
                        onClick={() => handleRenameSection(section.id)}
                      >
                        Save
                      </Button>
                    </div>
                  ) : singleSection ? (
                    <>
                      <h2 className={styles.sectionName}>{section.name}</h2>
                      <span className={styles.sectionCount}>
                        {section.packed_count} of {section.total_count}
                      </span>
                    </>
                  ) : (
                    <button
                      type="button"
                      className={styles.sectionToggle}
                      onClick={() => toggleSection(section.id)}
                      aria-expanded={!isCollapsed}
                    >
                      <span
                        className={`${styles.chevron} ${
                          isCollapsed ? styles.chevronCollapsed : ""
                        }`.trim()}
                        aria-hidden="true"
                      >
                        ▼
                      </span>
                      <h2 className={styles.sectionName}>{section.name}</h2>
                      {/* Collapsing hides items, never information — the
                          count stays. */}
                      <span className={styles.sectionCount}>
                        {section.packed_count} of {section.total_count}
                      </span>
                    </button>
                  )}
                  {editMode && (
                    <div className={styles.rowTools}>
                      <button
                        type="button"
                        className={styles.tool}
                        onClick={() => moveSection(section.id, sectionIndex - 1)}
                        disabled={sectionIndex === 0}
                        aria-label={`Move ${section.name} up`}
                      >
                        ↑
                      </button>
                      <button
                        type="button"
                        className={styles.tool}
                        onClick={() => moveSection(section.id, sectionIndex + 1)}
                        disabled={sectionIndex === detail.sections.length - 1}
                        aria-label={`Move ${section.name} down`}
                      >
                        ↓
                      </button>
                      <button
                        type="button"
                        className={styles.tool}
                        onClick={() => {
                          setSectionName(section.name);
                          setRenamingSectionId(section.id);
                        }}
                        aria-label={`Rename ${section.name}`}
                      >
                        ✏️
                      </button>
                      <button
                        type="button"
                        className={styles.tool}
                        onClick={() => handleDeleteSection(section)}
                        aria-label={`Delete ${section.name}`}
                      >
                        ✕
                      </button>
                    </div>
                  )}
                </div>
              )}

              {!singleSection && !isCollapsed && section.total_count > 0 && (
                <div className={styles.sectionTrack} aria-hidden="true">
                  <div
                    className={styles.sectionFill}
                    style={{
                      width: `${
                        section.total_count
                          ? Math.round(
                              (100 * section.packed_count) / section.total_count,
                            )
                          : 0
                      }%`,
                    }}
                  />
                </div>
              )}

              {!isCollapsed && (
                <>
                  <ul className={styles.items}>
                    {section.items.map((item, itemIndex) => (
                      <li key={item.id} className={styles.itemRow}>
                        <label
                          className={`${styles.itemLabel} ${item.packed ? styles.packed : ""}`.trim()}
                        >
                          <input
                            type="checkbox"
                            checked={item.packed}
                            onChange={(e) => togglePacked(item.id, e.target.checked)}
                            className={styles.checkbox}
                          />
                          <span className={styles.itemName}>
                            {item.name}
                            {item.quantity && (
                              <span className={styles.quantity}> × {item.quantity}</span>
                            )}
                          </span>
                          {!editMode && item.price !== null && (
                            <span className={styles.price}>
                              {formatMoney(item.price)}
                            </span>
                          )}
                        </label>
                        {item.notes && <p className={styles.notes}>{item.notes}</p>}
                        {editMode && (
                          <input
                            key={`${item.id}:${item.price ?? ""}`}
                            type="number"
                            inputMode="decimal"
                            min="0"
                            step="0.01"
                            defaultValue={item.price ?? ""}
                            placeholder="$"
                            aria-label={`Price for ${item.name}`}
                            className={styles.priceInput}
                            onBlur={(e) =>
                              commitPrice(item.id, e.target.value, item.price)
                            }
                            onKeyDown={(e) =>
                              e.key === "Enter" && e.currentTarget.blur()
                            }
                          />
                        )}
                        {editMode && (
                          <div className={styles.rowTools}>
                            <button
                              type="button"
                              className={styles.tool}
                              onClick={() => moveItem(item.id, itemIndex, itemIndex - 1)}
                              disabled={itemIndex === 0}
                              aria-label={`Move ${item.name} up`}
                            >
                              ↑
                            </button>
                            <button
                              type="button"
                              className={styles.tool}
                              onClick={() => moveItem(item.id, itemIndex, itemIndex + 1)}
                              disabled={itemIndex === section.items.length - 1}
                              aria-label={`Move ${item.name} down`}
                            >
                              ↓
                            </button>
                            <button
                              type="button"
                              className={styles.tool}
                              onClick={() => handleDeleteItem(item.id)}
                              aria-label={`Delete ${item.name}`}
                            >
                              ✕
                            </button>
                          </div>
                        )}
                      </li>
                    ))}
                  </ul>

                  <div className={styles.addRow}>
                    <input
                      type="text"
                      value={newItemBySection[section.id] ?? ""}
                      onChange={(e) =>
                        setNewItemBySection((m) => ({
                          ...m,
                          [section.id]: e.target.value,
                        }))
                      }
                      onKeyDown={(e) => e.key === "Enter" && handleAddItem(section)}
                      placeholder="Add an item…"
                      className={styles.addInput}
                    />
                    {(newItemBySection[section.id] ?? "").trim() && (
                      <Button variant="secondary" onClick={() => handleAddItem(section)}>
                        Add
                      </Button>
                    )}
                  </div>
                </>
              )}
            </section>
          );
        })}
      </div>

      <div className={styles.addRow}>
        <input
          type="text"
          value={newSection}
          onChange={(e) => setNewSection(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleAddSection()}
          placeholder="Add a section…"
          className={styles.addInput}
        />
        {newSection.trim() && (
          <Button variant="secondary" onClick={handleAddSection}>
            Add
          </Button>
        )}
      </div>

      {/* Deliberately quiet and far from the tap targets: archive stays
          the primary way to finish with a list. */}
      {editMode && (
        <button
          type="button"
          className={styles.deleteList}
          onClick={handleDeleteList}
        >
          Delete this list…
        </button>
      )}
    </AppShell>
  );
}
