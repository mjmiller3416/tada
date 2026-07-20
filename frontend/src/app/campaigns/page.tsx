"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import AuthGate from "@/components/AuthGate";
import {
  createCampaign,
  deleteCampaign,
  getCampaign,
  getCampaigns,
  getTasks,
  updateCampaign,
  type Campaign,
  type Task,
} from "@/lib/api";
import { NAV_ITEMS } from "@/lib/nav";
import { AppShell, Button, Card, Chip } from "@/components/ui";
import styles from "./campaigns.module.css";

/**
 * Seasonal campaigns (SPEC §6, Phase 3) — a planning surface. Bundle
 * tasks into a named project with a date window ("Spring Cleaning"),
 * activate it, and the home screen doles it out a few tasks a day with
 * a progress rollup. An overlay: the tasks stay ordinary decaying tasks.
 */
export default function CampaignsPage() {
  return <AuthGate ownerOnly>{() => <CampaignsScreen />}</AuthGate>;
}

function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function prettyDate(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString([], {
    month: "short",
    day: "numeric",
  });
}

/** Checkbox task picker grouped by room — shared by create and edit. */
function TaskPicker({
  tasks,
  selected,
  onToggle,
}: {
  tasks: Task[];
  selected: Set<number>;
  onToggle: (id: number) => void;
}) {
  const groups = useMemo(() => {
    const byRoom = new Map<string, Task[]>();
    for (const task of tasks) {
      const key = task.room_name ?? "No room";
      byRoom.set(key, [...(byRoom.get(key) ?? []), task]);
    }
    return [...byRoom.entries()];
  }, [tasks]);

  return (
    <div className={styles.picker}>
      {groups.map(([roomName, roomTasks]) => (
        <div key={roomName} className={styles.pickerGroup}>
          <p className={styles.pickerRoom}>{roomName}</p>
          {roomTasks.map((task) => (
            <label key={task.id} className={styles.pickerRow}>
              <input
                type="checkbox"
                checked={selected.has(task.id)}
                onChange={() => onToggle(task.id)}
              />
              <span className={styles.pickerName}>{task.name}</span>
              <span className={styles.pickerMeta}>{task.estimated_minutes} min</span>
            </label>
          ))}
        </div>
      ))}
    </div>
  );
}

function CampaignsScreen() {
  const router = useRouter();
  const [campaigns, setCampaigns] = useState<Campaign[] | null>(null);
  const [allTasks, setAllTasks] = useState<Task[]>([]);

  // ---- Create form ----
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [season, setSeason] = useState("");
  const [startDate, setStartDate] = useState(() => isoDate(new Date()));
  const [endDate, setEndDate] = useState(() =>
    isoDate(new Date(Date.now() + 29 * 86400000)),
  );
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ---- Per-campaign checklist editing ----
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editPicked, setEditPicked] = useState<Set<number>>(new Set());

  const load = useCallback(() => {
    getCampaigns()
      .then(setCampaigns)
      .catch(() => setCampaigns([]));
  }, []);

  useEffect(() => {
    load();
    getTasks()
      .then(setAllTasks)
      .catch(() => {});
  }, [load]);

  function toggle(set: Set<number>, id: number): Set<number> {
    const next = new Set(set);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  }

  async function handleCreate() {
    if (saving || !name.trim() || picked.size === 0) return;
    setSaving(true);
    setError(null);
    try {
      await createCampaign({
        name: name.trim(),
        season: season.trim() || undefined,
        start_date: startDate,
        end_date: endDate,
        task_ids: [...picked],
      });
      setCreating(false);
      setName("");
      setSeason("");
      setPicked(new Set());
      load();
    } catch {
      setError("Something hiccuped — check the dates and try again.");
    } finally {
      setSaving(false);
    }
  }

  async function handleToggleActive(campaign: Campaign) {
    await updateCampaign(campaign.id, { active: !campaign.active }).catch(() => {});
    load();
  }

  async function openEditor(campaign: Campaign) {
    if (editingId === campaign.id) {
      setEditingId(null);
      return;
    }
    try {
      const detail = await getCampaign(campaign.id);
      setEditPicked(new Set(detail.tasks.map((entry) => entry.task.id)));
      setEditingId(campaign.id);
    } catch {
      /* leave the editor closed */
    }
  }

  async function saveEditor(campaign: Campaign) {
    await updateCampaign(campaign.id, { task_ids: [...editPicked] }).catch(() => {});
    setEditingId(null);
    load();
  }

  async function handleDelete(campaign: Campaign) {
    if (!window.confirm(`Remove “${campaign.name}”? Its tasks stay — only the campaign goes.`))
      return;
    await deleteCampaign(campaign.id).catch(() => {});
    load();
  }

  return (
    <AppShell title="Campaigns" nav={NAV_ITEMS}>
      <p className={styles.help}>
        A campaign bundles tasks into one cozy project with a finish line —
        spring cleaning, holiday prep. Activate one and Tada spreads it over
        the days, a little at a time. 🌷
      </p>

      {!creating && (
        <Button variant="primary" fullWidth onClick={() => setCreating(true)}>
          Start a new campaign
        </Button>
      )}

      {creating && (
        <Card padding="lg" className={styles.formCard}>
          <h2 className={styles.formTitle}>New campaign</h2>

          <label className={styles.field}>
            <span className={styles.label}>Name</span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Spring Cleaning"
              className={styles.input}
            />
          </label>

          <label className={styles.field}>
            <span className={styles.label}>Season (optional)</span>
            <input
              type="text"
              value={season}
              onChange={(e) => setSeason(e.target.value)}
              placeholder="e.g. Spring"
              className={styles.input}
            />
          </label>

          <div className={styles.dateRow}>
            <label className={styles.field}>
              <span className={styles.label}>Starts</span>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className={styles.input}
              />
            </label>
            <label className={styles.field}>
              <span className={styles.label}>Wraps up</span>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className={styles.input}
              />
            </label>
          </div>

          <p className={styles.label}>
            Which tasks belong to it? ({picked.size} picked)
          </p>
          <TaskPicker
            tasks={allTasks}
            selected={picked}
            onToggle={(id) => setPicked((s) => toggle(s, id))}
          />

          {error && <p className={styles.error}>{error}</p>}

          <div className={styles.formActions}>
            <Button
              variant="primary"
              fullWidth
              disabled={saving || !name.trim() || picked.size === 0}
              onClick={handleCreate}
            >
              {saving ? "Saving…" : "Create campaign"}
            </Button>
            <Button variant="ghost" fullWidth onClick={() => setCreating(false)}>
              Never mind
            </Button>
          </div>
        </Card>
      )}

      <div className={styles.list}>
        {campaigns?.map((campaign) => (
          <Card key={campaign.id} className={styles.campaignCard}>
            <div className={styles.cardTop}>
              <div className={styles.titleWrap}>
                <span className={styles.name}>{campaign.name}</span>
                {campaign.season && <Chip tone="lavender">{campaign.season}</Chip>}
              </div>
              <button
                type="button"
                className={styles.remove}
                onClick={() => handleDelete(campaign)}
                aria-label={`Remove ${campaign.name}`}
              >
                ✕
              </button>
            </div>

            <p className={styles.window}>
              {prettyDate(campaign.start_date)} – {prettyDate(campaign.end_date)}
              {campaign.is_running && " · happening now"}
            </p>

            <div
              className={styles.progressTrack}
              role="progressbar"
              aria-valuenow={campaign.percent}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div
                className={styles.progressFill}
                style={{ width: `${campaign.percent}%` }}
              />
            </div>
            <p className={styles.progressText}>
              {campaign.done_tasks} of {campaign.total_tasks} done ({campaign.percent}%)
            </p>

            <div className={styles.actions}>
              <Chip
                tone={campaign.active ? "mint" : "neutral"}
                onClick={() => handleToggleActive(campaign)}
              >
                {campaign.active ? "Active ✓" : "Paused"}
              </Chip>
              <Chip tone="neutral" onClick={() => openEditor(campaign)}>
                {editingId === campaign.id ? "Close" : "Edit tasks"}
              </Chip>
              {campaign.is_running && campaign.percent < 100 && (
                <Button
                  variant="secondary"
                  onClick={() =>
                    router.push(
                      `/session?campaign=${campaign.id}&label=${encodeURIComponent(campaign.name)}`,
                    )
                  }
                >
                  Work on it
                </Button>
              )}
            </div>

            {editingId === campaign.id && (
              <div className={styles.editor}>
                <TaskPicker
                  tasks={allTasks}
                  selected={editPicked}
                  onToggle={(id) => setEditPicked((s) => toggle(s, id))}
                />
                <Button
                  variant="primary"
                  fullWidth
                  disabled={editPicked.size === 0}
                  onClick={() => saveEditor(campaign)}
                >
                  Save checklist
                </Button>
              </div>
            )}
          </Card>
        ))}

        {campaigns !== null && campaigns.length === 0 && !creating && (
          <Card padding="lg" className={styles.emptyCard}>
            <p className={styles.emptyText}>
              No campaigns yet. When a big season rolls around — spring
              cleaning, holidays — start one here and Tada will pace it
              out for you, no overwhelm.
            </p>
          </Card>
        )}
      </div>
    </AppShell>
  );
}
