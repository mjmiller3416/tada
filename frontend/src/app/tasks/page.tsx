"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import AuthGate from "@/components/AuthGate";
import TaskForm from "@/components/TaskForm";
import TaskRow from "@/components/TaskRow";
import {
  completeTask,
  getMembers,
  getRooms,
  getTasks,
  type Category,
  type Effort,
  type Member,
  type Room,
  type Task,
} from "@/lib/api";
import { NAV_ITEMS } from "@/lib/nav";
import { AppShell, Button, Card, Chip } from "@/components/ui";
import styles from "./tasks.module.css";

type SortMode = "dirtiest" | "name" | "room";
type EffortFilter = Effort | "all";
type AssigneeFilter = number | "all";

function parseAssignee(param: string | null): AssigneeFilter {
  const id = Number(param);
  return param !== null && Number.isInteger(id) && id > 0 ? id : "all";
}

/**
 * The Task/global view (SPEC §6): one flat list across the whole home,
 * sortable and filterable — the other planning surface. The API returns
 * tasks dirtiest-first; other sorts are client-side. Maintenance lives in
 * its own section (SPEC §6, Phase 2) so it never clutters daily cleaning,
 * and gets checked off right here — it never joins focus sessions.
 * Deep-linkable by person (Phase 4.6): /tasks?assignee=N is where the
 * "Your crew" rows in Settings land.
 */
export default function TasksPage() {
  return (
    <AuthGate ownerOnly>
      {() => (
        <Suspense fallback={null}>
          <TasksScreen />
        </Suspense>
      )}
    </AuthGate>
  );
}

function TasksScreen() {
  const searchParams = useSearchParams();
  const assigneeParam = searchParams.get("assignee");

  const [tasks, setTasks] = useState<Task[] | null>(null);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [category, setCategory] = useState<Category>("cleaning");
  const [roomFilter, setRoomFilter] = useState<number | "all">("all");
  const [effortFilter, setEffortFilter] = useState<EffortFilter>("all");
  const [assigneeFilter, setAssigneeFilter] = useState<AssigneeFilter>(() =>
    parseAssignee(assigneeParam),
  );
  const [sort, setSort] = useState<SortMode>("dirtiest");
  const [editing, setEditing] = useState<Task | null>(null);
  const [showForm, setShowForm] = useState(false);

  // Arriving via a crew link while already mounted still applies the
  // person from the URL.
  useEffect(() => {
    setAssigneeFilter(parseAssignee(assigneeParam));
  }, [assigneeParam]);

  const load = useCallback(() => {
    getTasks({ include_inactive: true })
      .then(setTasks)
      .catch(() => setTasks([]));
    getRooms()
      .then(setRooms)
      .catch(() => {});
    getMembers()
      .then(setMembers)
      .catch(() => {});
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const visible = useMemo(() => {
    if (!tasks) return [];
    // The cleaning/maintenance split reads task_type now (Phase 10):
    // "maintenance" is the maintenance lane, "cleaning" everything else.
    let list = tasks.filter((t) =>
      category === "maintenance"
        ? t.task_type === "maintenance"
        : t.task_type !== "maintenance",
    );
    if (roomFilter !== "all") list = list.filter((t) => t.room_id === roomFilter);
    if (effortFilter !== "all") list = list.filter((t) => t.effort === effortFilter);
    if (assigneeFilter !== "all")
      list = list.filter((t) => t.assignee_id === assigneeFilter);
    if (sort === "name") {
      list = [...list].sort((a, b) => a.name.localeCompare(b.name));
    } else if (sort === "room") {
      list = [...list].sort((a, b) =>
        (a.room_name ?? "~").localeCompare(b.room_name ?? "~"),
      );
    }
    return list; // "dirtiest" keeps the API's priority order
  }, [tasks, category, roomFilter, effortFilter, assigneeFilter, sort]);

  function closeForm(changed: boolean) {
    setShowForm(false);
    setEditing(null);
    if (changed) load();
  }

  async function handleMaintenanceDone(task: Task) {
    try {
      await completeTask(task.id, "direct");
    } finally {
      load();
    }
  }

  return (
    <AppShell title="All tasks" nav={NAV_ITEMS}>
      <div className={styles.controls}>
        <div className={styles.chipRow}>
          <Chip
            tone={category === "cleaning" ? "coral" : "neutral"}
            onClick={() => setCategory("cleaning")}
          >
            🧽 Cleaning
          </Chip>
          <Chip
            tone={category === "maintenance" ? "coral" : "neutral"}
            onClick={() => setCategory("maintenance")}
          >
            🔧 Maintenance
          </Chip>
        </div>

        <div className={styles.filterRow}>
          <select
            value={roomFilter === "all" ? "all" : String(roomFilter)}
            onChange={(e) =>
              setRoomFilter(e.target.value === "all" ? "all" : Number(e.target.value))
            }
            className={styles.select}
            aria-label="Filter by room"
          >
            <option value="all">All rooms</option>
            {rooms.map((room) => (
              <option key={room.id} value={room.id}>
                {room.name}
              </option>
            ))}
          </select>

          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as SortMode)}
            className={styles.select}
            aria-label="Sort"
          >
            <option value="dirtiest">Needs love first</option>
            <option value="name">A to Z</option>
            <option value="room">By room</option>
          </select>
        </div>

        {/* Whose plate? (Phase 4.6) — only once there's more than one
            person to tell apart. */}
        {members.length > 1 && (
          <div className={styles.filterRow}>
            <select
              value={assigneeFilter === "all" ? "all" : String(assigneeFilter)}
              onChange={(e) =>
                setAssigneeFilter(
                  e.target.value === "all" ? "all" : Number(e.target.value),
                )
              }
              className={styles.select}
              aria-label="Filter by person"
            >
              <option value="all">Everyone’s tasks</option>
              {members.map((member) => (
                <option key={member.id} value={member.id}>
                  Assigned to {member.name}
                </option>
              ))}
            </select>
          </div>
        )}

        <div className={styles.chipRow}>
          <Chip
            tone={effortFilter === "all" ? "coral" : "neutral"}
            onClick={() => setEffortFilter("all")}
          >
            Everything
          </Chip>
          <Chip
            tone={effortFilter === "quick" ? "coral" : "neutral"}
            onClick={() => setEffortFilter("quick")}
          >
            Quick wins
          </Chip>
          <Chip
            tone={effortFilter === "deep" ? "coral" : "neutral"}
            onClick={() => setEffortFilter("deep")}
          >
            Deep cleans
          </Chip>
        </div>
      </div>

      <Button
        variant="secondary"
        fullWidth
        onClick={() => {
          setEditing(null);
          setShowForm(true);
        }}
      >
        + Add a task
      </Button>

      <div className={styles.list}>
        {visible.map((task) => (
          <TaskRow
            key={task.id}
            task={task}
            onDone={
              category === "maintenance" && task.is_active
                ? () => handleMaintenanceDone(task)
                : undefined
            }
            onClick={() => {
              setEditing(task);
              setShowForm(true);
            }}
            onTypeChanged={load}
          />
        ))}
        {tasks !== null && visible.length === 0 && (
          <Card padding="lg" className={styles.emptyCard}>
            <p className={styles.emptyText}>
              {tasks.length === 0
                ? "No tasks yet — run the setup wizard or add one above."
                : category === "maintenance"
                  ? "No maintenance tasks yet — think HVAC filters, smoke-alarm batteries, gutters."
                  : "Nothing matches those filters."}
            </p>
          </Card>
        )}
      </div>

      {showForm && (
        <TaskForm
          task={editing}
          rooms={rooms}
          defaultTaskType={category === "maintenance" ? "maintenance" : "routine"}
          onClose={closeForm}
        />
      )}
    </AppShell>
  );
}
