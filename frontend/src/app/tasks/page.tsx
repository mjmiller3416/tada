"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import AuthGate from "@/components/AuthGate";
import TaskForm from "@/components/TaskForm";
import TaskRow from "@/components/TaskRow";
import { getRooms, getTasks, type Effort, type Room, type Task } from "@/lib/api";
import { NAV_ITEMS } from "@/lib/nav";
import { AppShell, Button, Card, Chip } from "@/components/ui";
import styles from "./tasks.module.css";

type SortMode = "dirtiest" | "name" | "room";
type EffortFilter = Effort | "all";

/**
 * The Task/global view (SPEC §6): one flat list across the whole home,
 * sortable and filterable — the other planning surface. The API returns
 * tasks dirtiest-first; other sorts are client-side.
 */
export default function TasksPage() {
  return <AuthGate>{() => <TasksScreen />}</AuthGate>;
}

function TasksScreen() {
  const [tasks, setTasks] = useState<Task[] | null>(null);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [roomFilter, setRoomFilter] = useState<number | "all">("all");
  const [effortFilter, setEffortFilter] = useState<EffortFilter>("all");
  const [sort, setSort] = useState<SortMode>("dirtiest");
  const [editing, setEditing] = useState<Task | null>(null);
  const [showForm, setShowForm] = useState(false);

  const load = useCallback(() => {
    getTasks({ include_inactive: true })
      .then(setTasks)
      .catch(() => setTasks([]));
    getRooms()
      .then(setRooms)
      .catch(() => {});
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const visible = useMemo(() => {
    if (!tasks) return [];
    let list = tasks;
    if (roomFilter !== "all") list = list.filter((t) => t.room_id === roomFilter);
    if (effortFilter !== "all") list = list.filter((t) => t.effort === effortFilter);
    if (sort === "name") {
      list = [...list].sort((a, b) => a.name.localeCompare(b.name));
    } else if (sort === "room") {
      list = [...list].sort((a, b) =>
        (a.room_name ?? "~").localeCompare(b.room_name ?? "~"),
      );
    }
    return list; // "dirtiest" keeps the API's priority order
  }, [tasks, roomFilter, effortFilter, sort]);

  function closeForm(changed: boolean) {
    setShowForm(false);
    setEditing(null);
    if (changed) load();
  }

  return (
    <AppShell title="All tasks" nav={NAV_ITEMS}>
      <div className={styles.controls}>
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
            onClick={() => {
              setEditing(task);
              setShowForm(true);
            }}
          />
        ))}
        {tasks !== null && visible.length === 0 && (
          <Card padding="lg" className={styles.emptyCard}>
            <p className={styles.emptyText}>
              {tasks.length === 0
                ? "No tasks yet — run the setup wizard or add one above."
                : "Nothing matches those filters."}
            </p>
          </Card>
        )}
      </div>

      {showForm && <TaskForm task={editing} rooms={rooms} onClose={closeForm} />}
    </AppShell>
  );
}
