"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import AuthGate from "@/components/AuthGate";
import {
  createList,
  deleteList,
  getLists,
  getListTemplates,
  updateList,
  type ListSummary,
} from "@/lib/api";
import { NAV_ITEMS } from "@/lib/nav";
import {
  checkedVerb,
  countdownLabel,
  formatMoney,
  LIST_KIND_META,
  prettyEventDate,
  templateEmoji,
} from "@/lib/lists";
import { AppShell, Button, Card, Chip } from "@/components/ui";
import styles from "./lists.module.css";

/**
 * Lists index (Phase 6, grown from Phase 4 packing) — its own section,
 * parallel to the cleaning surfaces and never mixed into them. Active
 * lists up top with progress; archived lists tucked away below,
 * restorable and reusable. Unlike cleaning, this is a full-checklist
 * world: tapping a list opens the whole grouped checklist, never a
 * one-at-a-time flow.
 */
export default function ListsPage() {
  return <AuthGate ownerOnly>{() => <ListsScreen />}</AuthGate>;
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

function ListsScreen() {
  const router = useRouter();
  const [lists, setLists] = useState<ListSummary[] | null>(null);

  // ---- "New list" flow: pick a template, then name/date it ----
  const [picking, setPicking] = useState(false);
  const [templates, setTemplates] = useState<ListSummary[]>([]);
  const [chosen, setChosen] = useState<ListSummary | null>(null);
  const [name, setName] = useState("");
  const [eventDate, setEventDate] = useState("");
  const [destination, setDestination] = useState("");
  const [duration, setDuration] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [showArchived, setShowArchived] = useState(false);

  const load = useCallback(() => {
    getLists()
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
        setTemplates(await getListTemplates());
      } catch {
        setError("Couldn't load the starter templates — try again in a sec.");
        setPicking(false);
      }
    }
  }

  function choose(template: ListSummary) {
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
      const created = await createList({
        source_list_id: sourceId,
        name: listName.trim() || undefined,
        event_date: date || undefined,
        destination: dest.trim() || undefined,
        duration: length.trim() || undefined,
      });
      router.push(`/lists/${created.id}`);
    } catch {
      setError("Something hiccuped creating the list — try again.");
      setSaving(false);
    }
  }

  async function handleRestore(list: ListSummary) {
    await updateList(list.id, { status: "active" }).catch(() => {});
    load();
  }

  async function handleDelete(list: ListSummary) {
    const count = list.total_count;
    const message =
      count > 0
        ? `Delete “${list.name}” and its ${count} ${count === 1 ? "item" : "items"}? This can't be undone.`
        : `Delete “${list.name}”? This can't be undone.`;
    if (!window.confirm(message)) return;
    await deleteList(list.id).catch(() => {});
    load();
  }

  const active = (lists ?? []).filter((list) => list.status === "active");
  const archived = (lists ?? []).filter((list) => list.status === "archived");

  return (
    <AppShell title="Lists" nav={NAV_ITEMS}>
      <p className={styles.help}>
        Checklists for everything one-off — trips, gifts, school
        supplies, projects. The whole list at a glance so nothing gets
        forgotten. Start from a template and make it yours. 📋
      </p>

      {!picking && (
        <Button variant="primary" fullWidth onClick={openPicker}>
          Start a new list
        </Button>
      )}

      {picking && !chosen && (
        <Card padding="lg" className={styles.pickerCard}>
          <h2 className={styles.formTitle}>What kind of list?</h2>
          <div className={styles.templateGrid}>
            {templates.map((template) => (
              <button
                key={template.id}
                type="button"
                className={styles.templateTile}
                onClick={() => choose(template)}
              >
                <span className={styles.templateEmoji} aria-hidden="true">
                  {templateEmoji(template.name, template.kind)}
                </span>
                <span className={styles.templateName}>{template.name}</span>
                <span className={styles.templateCount}>
                  {template.total_count > 0
                    ? `${template.total_count} starter items`
                    : "start from scratch"}
                </span>
              </button>
            ))}
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
            {templateEmoji(chosen.name, chosen.kind)} New {chosen.name.toLowerCase()}{" "}
            list
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
              {chosen.kind === "packing"
                ? "Trip or move date (optional — for a friendly countdown)"
                : "Need it by a date? (optional — for a friendly countdown)"}
            </span>
            <input
              type="date"
              value={eventDate}
              onChange={(e) => setEventDate(e.target.value)}
              className={styles.input}
            />
          </label>

          {chosen.kind === "packing" && (
            <>
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
            </>
          )}

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
          const meta = LIST_KIND_META[list.kind];
          const countdown = list.event_date ? countdownLabel(list.event_date) : null;
          return (
            <Card
              key={list.id}
              className={styles.listCard}
              onClick={() => router.push(`/lists/${list.id}`)}
              role="link"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter") router.push(`/lists/${list.id}`);
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
                {list.packed_count} of {list.total_count} {checkedVerb(list.kind)}
                {list.percent === 100 && " — all set! 🎉"}
              </p>
              {list.total_price !== null && list.checked_price !== null && (
                <p className={styles.totals}>
                  💵 {formatMoney(list.checked_price)} of{" "}
                  {formatMoney(list.total_price)}
                </p>
              )}
            </Card>
          );
        })}

        {lists !== null && active.length === 0 && !picking && (
          <Card padding="lg" className={styles.emptyCard}>
            <p className={styles.emptyText}>
              No lists on the go right now. When a trip, gift season, or
              project is coming up, start one from a template and check
              things off as you go.
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
              const meta = LIST_KIND_META[list.kind];
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
