"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import AuthGate from "@/components/AuthGate";
import {
  addPackingItem,
  addPackingSection,
  deletePackingItem,
  deletePackingSection,
  updatePackingItem,
  updatePackingList,
  updatePackingSection,
  getPackingList,
  type PackingListDetail,
  type PackingSection,
} from "@/lib/api";
import { NAV_ITEMS } from "@/lib/nav";
import {
  countdownLabel,
  PACKING_CATEGORY_META,
  prettyEventDate,
} from "@/lib/packing";
import { AppShell, Button, Card, Chip, Confetti } from "@/components/ui";
import styles from "./list-detail.module.css";

/**
 * One packing list as a FULL grouped checklist (Phase 4) — deliberately
 * NOT the one-task-at-a-time focus flow. Packing is the place seeing
 * everything wins: sections as headers, checkboxes beneath, progress up
 * top, and a little confetti when the last item is packed.
 */
export default function PackingListPage() {
  return <AuthGate ownerOnly>{() => <PackingListScreen />}</AuthGate>;
}

function PackingListScreen() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const listId = Number(params.id);

  const [detail, setDetail] = useState<PackingListDetail | null>(null);
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

  useEffect(() => {
    getPackingList(listId)
      .then((d) => {
        prevPercent.current = d.percent;
        setDetail(d);
        setDestinationDraft(d.destination ?? "");
        setDurationDraft(d.duration ?? "");
      })
      .catch(() => setMissing(true));
  }, [listId]);

  /** Every mutation returns the canonical full list — one setter for all. */
  function apply(next: PackingListDetail) {
    if (
      prevPercent.current !== null &&
      prevPercent.current < 100 &&
      next.percent === 100 &&
      next.total_count > 0
    ) {
      setCelebrating(true);
    }
    prevPercent.current = next.percent;
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
      apply(await updatePackingItem(itemId, { packed }));
    } catch {
      apply(await getPackingList(listId).catch(() => detail));
    }
  }

  async function handleAddItem(section: PackingSection) {
    const name = (newItemBySection[section.id] ?? "").trim();
    if (!name || !detail) return;
    setNewItemBySection((m) => ({ ...m, [section.id]: "" }));
    apply(await addPackingItem(section.id, { name }).catch(() => detail));
  }

  async function handleAddSection() {
    const name = newSection.trim();
    if (!name || !detail) return;
    setNewSection("");
    apply(await addPackingSection(listId, name).catch(() => detail));
  }

  async function handleRename() {
    if (!detail || !newName.trim()) return;
    setRenaming(false);
    apply(await updatePackingList(listId, { name: newName.trim() }).catch(() => detail));
  }

  async function handleRenameSection(sectionId: number) {
    if (!detail || !sectionName.trim()) return;
    setRenamingSectionId(null);
    apply(
      await updatePackingSection(sectionId, { name: sectionName.trim() }).catch(
        () => detail,
      ),
    );
  }

  async function handleDeleteItem(itemId: number) {
    if (!detail) return;
    apply(await deletePackingItem(itemId).catch(() => detail));
  }

  async function handleDeleteSection(section: PackingSection) {
    if (!detail) return;
    if (
      section.items.length > 0 &&
      !window.confirm(`Remove “${section.name}” and its ${section.items.length} items?`)
    )
      return;
    apply(await deletePackingSection(section.id).catch(() => detail));
  }

  async function moveItem(itemId: number, from: number, to: number) {
    if (!detail || to < 0) return;
    void from;
    apply(await updatePackingItem(itemId, { sort_order: to }).catch(() => detail));
  }

  async function moveSection(sectionId: number, to: number) {
    if (!detail || to < 0) return;
    apply(await updatePackingSection(sectionId, { sort_order: to }).catch(() => detail));
  }

  async function handleEventDate(value: string) {
    if (!detail) return;
    apply(
      await updatePackingList(
        listId,
        value ? { event_date: value } : { clear_event_date: true },
      ).catch(() => detail),
    );
  }

  async function commitDestination() {
    if (!detail) return;
    const value = destinationDraft.trim();
    if (value === (detail.destination ?? "")) return;
    const next = await updatePackingList(
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
    const next = await updatePackingList(
      listId,
      value ? { duration: value } : { clear_duration: true },
    ).catch(() => detail);
    apply(next);
    setDurationDraft(next.duration ?? "");
  }

  async function toggleReminder() {
    if (!detail) return;
    apply(
      await updatePackingList(listId, {
        reminder_enabled: !detail.reminder_enabled,
      }).catch(() => detail),
    );
  }

  async function toggleArchive() {
    if (!detail) return;
    const next = detail.status === "active" ? "archived" : "active";
    apply(await updatePackingList(listId, { status: next }).catch(() => detail));
    if (next === "archived") router.push("/packing");
  }

  if (missing) {
    return (
      <AppShell title="Packing" nav={NAV_ITEMS}>
        <Card padding="lg">
          <p className={styles.emptyText}>
            Hmm, that list isn&apos;t here anymore.
          </p>
          <Button variant="secondary" fullWidth onClick={() => router.push("/packing")}>
            Back to packing
          </Button>
        </Card>
      </AppShell>
    );
  }

  if (!detail) {
    return <AppShell title="Packing" nav={NAV_ITEMS}>{null}</AppShell>;
  }

  const meta = PACKING_CATEGORY_META[detail.category];
  const countdown = detail.event_date ? countdownLabel(detail.event_date) : null;
  const remaining = detail.total_count - detail.packed_count;

  return (
    <AppShell nav={NAV_ITEMS}>
      <Confetti active={celebrating} onComplete={() => setCelebrating(false)} />

      <button
        type="button"
        className={styles.back}
        onClick={() => router.push("/packing")}
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
            ? "All packed — you're all set! 🎉"
            : `${detail.packed_count} of ${detail.total_count} packed` +
              (remaining > 0 ? ` · ${remaining} to go` : "")}
        </p>

        <div className={styles.eventRow}>
          <label className={styles.eventLabel}>
            <span className={styles.label}>Event date</span>
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
        {detail.sections.map((section, sectionIndex) => (
          <section key={section.id} className={styles.section}>
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
              ) : (
                <h2 className={styles.sectionName}>{section.name}</h2>
              )}
              <span className={styles.sectionCount}>
                {section.packed_count}/{section.total_count}
              </span>
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

            {section.total_count > 0 && (
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
                  </label>
                  {item.notes && <p className={styles.notes}>{item.notes}</p>}
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
          </section>
        ))}
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
    </AppShell>
  );
}
