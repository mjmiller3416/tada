"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import AuthGate from "@/components/AuthGate";
import {
  createPackingList,
  deletePackingList,
  getPackingLists,
  getPackingTemplates,
  updatePackingList,
  type PackingListSummary,
} from "@/lib/api";
import { NAV_ITEMS } from "@/lib/nav";
import {
  countdownLabel,
  PACKING_CATEGORY_META,
  prettyEventDate,
} from "@/lib/packing";
import { AppShell, Button, Card, Chip } from "@/components/ui";
import styles from "./packing.module.css";

/**
 * Packing lists index (Phase 4) — its own section, parallel to the
 * cleaning surfaces and never mixed into them. Active lists up top with
 * progress; archived lists tucked away below, restorable and reusable.
 * Unlike cleaning, packing is a full-checklist world: tapping a list
 * opens the whole grouped checklist, never a one-at-a-time flow.
 */
export default function PackingPage() {
  return <AuthGate ownerOnly>{() => <PackingScreen />}</AuthGate>;
}

function ProgressBar({ percent }: { percent: number }) {
  return (
    <div
      className={styles.progressTrack}
      role="progressbar"
      aria-valuenow={percent}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div className={styles.progressFill} style={{ width: `${percent}%` }} />
    </div>
  );
}

function PackingScreen() {
  const router = useRouter();
  const [lists, setLists] = useState<PackingListSummary[] | null>(null);

  // ---- "New list" flow: pick a template, then name/date it ----
  const [picking, setPicking] = useState(false);
  const [templates, setTemplates] = useState<PackingListSummary[]>([]);
  const [chosen, setChosen] = useState<PackingListSummary | null>(null);
  const [name, setName] = useState("");
  const [eventDate, setEventDate] = useState("");
  const [destination, setDestination] = useState("");
  const [duration, setDuration] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [showArchived, setShowArchived] = useState(false);

  const load = useCallback(() => {
    getPackingLists()
      .then(setLists)
      .catch(() => setLists([]));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function openPicker() {
    setPicking(true);
    setChosen(null);
    if (templates.length === 0) {
      try {
        setTemplates(await getPackingTemplates());
      } catch {
        setError("Couldn't load the starter templates — try again in a sec.");
        setPicking(false);
      }
    }
  }

  function choose(template: PackingListSummary) {
    setChosen(template);
    setName(template.name);
    setEventDate("");
    setDestination("");
    setDuration("");
    setError(null);
  }

  async function handleCreate(
    sourceId: number,
    listName: string,
    date: string,
    dest = "",
    length = "",
  ) {
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      const created = await createPackingList({
        source_list_id: sourceId,
        name: listName.trim() || undefined,
        event_date: date || undefined,
        destination: dest.trim() || undefined,
        duration: length.trim() || undefined,
      });
      router.push(`/packing/${created.id}`);
    } catch {
      setError("Something hiccuped creating the list — try again.");
      setSaving(false);
    }
  }

  async function handleRestore(list: PackingListSummary) {
    await updatePackingList(list.id, { status: "active" }).catch(() => {});
    load();
  }

  async function handleDelete(list: PackingListSummary) {
    if (!window.confirm(`Delete “${list.name}” for good? Archiving keeps it around instead.`))
      return;
    await deletePackingList(list.id).catch(() => {});
    load();
  }

  const active = (lists ?? []).filter((list) => list.status === "active");
  const archived = (lists ?? []).filter((list) => list.status === "archived");

  return (
    <AppShell title="Packing" nav={NAV_ITEMS}>
      <p className={styles.help}>
        Checklists for trips, moves, and go-bags — the whole list at a
        glance so nothing gets forgotten. Start from a template and make
        it yours. 🧳
      </p>

      {!picking && (
        <Button variant="primary" fullWidth onClick={openPicker}>
          Start a new list
        </Button>
      )}

      {picking && !chosen && (
        <Card padding="lg" className={styles.pickerCard}>
          <h2 className={styles.formTitle}>What are you packing for?</h2>
          <div className={styles.templateGrid}>
            {templates.map((template) => {
              const meta = PACKING_CATEGORY_META[template.category];
              return (
                <button
                  key={template.id}
                  type="button"
                  className={styles.templateTile}
                  onClick={() => choose(template)}
                >
                  <span className={styles.templateEmoji} aria-hidden="true">
                    {meta.emoji}
                  </span>
                  <span className={styles.templateName}>{template.name}</span>
                  <span className={styles.templateCount}>
                    {template.total_count > 0
                      ? `${template.total_count} starter items`
                      : "start from scratch"}
                  </span>
                </button>
              );
            })}
          </div>
          {templates.length === 0 && (
            <p className={styles.emptyText}>Loading templates…</p>
          )}
          <Button variant="ghost" fullWidth onClick={() => setPicking(false)}>
            Never mind
          </Button>
        </Card>
      )}

      {picking && chosen && (
        <Card padding="lg" className={styles.pickerCard}>
          <h2 className={styles.formTitle}>
            {PACKING_CATEGORY_META[chosen.category].emoji} New{" "}
            {PACKING_CATEGORY_META[chosen.category].label.toLowerCase()} list
          </h2>

          <label className={styles.field}>
            <span className={styles.label}>Name</span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={chosen.name}
              className={styles.input}
            />
          </label>

          <label className={styles.field}>
            <span className={styles.label}>
              Trip or move date (optional — for a friendly countdown)
            </span>
            <input
              type="date"
              value={eventDate}
              onChange={(e) => setEventDate(e.target.value)}
              className={styles.input}
            />
          </label>

          <label className={styles.field}>
            <span className={styles.label}>Destination (optional)</span>
            <input
              type="text"
              value={destination}
              onChange={(e) => setDestination(e.target.value)}
              placeholder="Where to? e.g. Orlando"
              className={styles.input}
            />
          </label>

          <label className={styles.field}>
            <span className={styles.label}>How long? (optional)</span>
            <input
              type="text"
              value={duration}
              onChange={(e) => setDuration(e.target.value)}
              placeholder="e.g. 5 days, a long weekend"
              className={styles.input}
            />
          </label>

          {error && <p className={styles.error}>{error}</p>}

          <div className={styles.formActions}>
            <Button
              variant="primary"
              fullWidth
              disabled={saving}
              onClick={() =>
                handleCreate(chosen.id, name, eventDate, destination, duration)
              }
            >
              {saving ? "Creating…" : "Create list"}
            </Button>
            <Button variant="ghost" fullWidth onClick={() => setChosen(null)}>
              Back to templates
            </Button>
          </div>
        </Card>
      )}

      <div className={styles.list}>
        {active.map((list) => {
          const meta = PACKING_CATEGORY_META[list.category];
          const countdown = list.event_date ? countdownLabel(list.event_date) : null;
          return (
            <Card
              key={list.id}
              className={styles.listCard}
              onClick={() => router.push(`/packing/${list.id}`)}
              role="link"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter") router.push(`/packing/${list.id}`);
              }}
            >
              <div className={styles.cardTop}>
                <span className={styles.listName}>{list.name}</span>
                <Chip tone={meta.tone}>
                  {meta.emoji} {meta.label}
                </Chip>
              </div>
              {(list.destination || list.duration || list.event_date) && (
                <p className={styles.eventLine}>
                  {[
                    list.destination && `📍 ${list.destination}`,
                    list.duration,
                    list.event_date &&
                      prettyEventDate(list.event_date) +
                        (countdown ? ` · ${countdown}` : ""),
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              )}
              <ProgressBar percent={list.percent} />
              <p className={styles.progressText}>
                {list.packed_count} of {list.total_count} packed
                {list.percent === 100 && " — all set! 🎉"}
              </p>
            </Card>
          );
        })}

        {lists !== null && active.length === 0 && !picking && (
          <Card padding="lg" className={styles.emptyCard}>
            <p className={styles.emptyText}>
              No lists on the go right now. When a trip, move, or busy
              season is coming, start one from a template and check
              things off as you pack.
            </p>
          </Card>
        )}
      </div>

      {archived.length > 0 && (
        <div className={styles.archivedBlock}>
          <button
            type="button"
            className={styles.archivedToggle}
            onClick={() => setShowArchived((v) => !v)}
          >
            {showArchived ? "Hide" : "Show"} archived lists ({archived.length})
          </button>

          {showArchived &&
            archived.map((list) => {
              const meta = PACKING_CATEGORY_META[list.category];
              return (
                <Card key={list.id} className={styles.archivedCard}>
                  <div className={styles.cardTop}>
                    <span className={styles.archivedName}>
                      {meta.emoji} {list.name}
                    </span>
                    <button
                      type="button"
                      className={styles.remove}
                      onClick={() => handleDelete(list)}
                      aria-label={`Delete ${list.name}`}
                    >
                      ✕
                    </button>
                  </div>
                  <div className={styles.archivedActions}>
                    <Chip
                      tone="mint"
                      onClick={() =>
                        handleCreate(list.id, `${list.name} (again)`, "")
                      }
                    >
                      Use again
                    </Chip>
                    <Chip tone="neutral" onClick={() => handleRestore(list)}>
                      Restore
                    </Chip>
                  </div>
                </Card>
              );
            })}
        </div>
      )}
    </AppShell>
  );
}
