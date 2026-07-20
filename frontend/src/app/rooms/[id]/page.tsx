"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import AuthGate from "@/components/AuthGate";
import TaskForm from "@/components/TaskForm";
import TaskRow from "@/components/TaskRow";
import DirtinessDot from "@/components/DirtinessDot";
import {
  deleteRoom,
  getRooms,
  getTasks,
  updateRoom,
  type Room,
  type Task,
} from "@/lib/api";
import { NAV_ITEMS } from "@/lib/nav";
import { AppShell, Button, Card } from "@/components/ui";
import styles from "./room-detail.module.css";

/**
 * One room's planning page: its tasks (everything, including fresh and
 * resting — this is organizing, not doing), a session launcher, and room
 * management (rename / remove).
 */
export default function RoomDetailPage() {
  return <AuthGate>{() => <RoomDetailScreen />}</AuthGate>;
}

function RoomDetailScreen() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const roomId = Number(params.id);

  const [rooms, setRooms] = useState<Room[]>([]);
  const [tasks, setTasks] = useState<Task[] | null>(null);
  const [editing, setEditing] = useState<Task | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [newName, setNewName] = useState("");

  const room = rooms.find((r) => r.id === roomId);

  const load = useCallback(() => {
    getRooms()
      .then(setRooms)
      .catch(() => {});
    getTasks({ room_id: roomId, include_inactive: true })
      .then(setTasks)
      .catch(() => setTasks([]));
  }, [roomId]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleRename(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    await updateRoom(roomId, { name: newName.trim() });
    setRenaming(false);
    load();
  }

  async function handleDeleteRoom() {
    if (
      !window.confirm(
        "Remove this room? Its tasks stay in your task list, just without a room.",
      )
    )
      return;
    await deleteRoom(roomId);
    router.replace("/rooms");
  }

  function closeForm(changed: boolean) {
    setShowForm(false);
    setEditing(null);
    if (changed) load();
  }

  const hasWork = room != null && room.due_count > 0;

  return (
    <AppShell title={room?.name ?? "Room"} nav={NAV_ITEMS}>
      {room?.band && (
        <div className={styles.summary}>
          <DirtinessDot band={room.band} withLabel />
        </div>
      )}

      {hasWork && (
        <Button
          variant="primary"
          size="lg"
          fullWidth
          onClick={() => router.push(`/session?room=${roomId}`)}
        >
          Clean this room
        </Button>
      )}

      <div className={styles.taskList}>
        {tasks?.map((task) => (
          <TaskRow
            key={task.id}
            task={task}
            hideRoom
            onClick={() => {
              setEditing(task);
              setShowForm(true);
            }}
          />
        ))}
        {tasks !== null && tasks.length === 0 && (
          <Card padding="lg" className={styles.emptyCard}>
            <p className={styles.emptyText}>No tasks in here yet.</p>
          </Card>
        )}
      </div>

      <div className={styles.actions}>
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

        {renaming ? (
          <form onSubmit={handleRename} className={styles.renameForm}>
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              className={styles.input}
              autoFocus
            />
            <Button type="submit" variant="primary" disabled={!newName.trim()}>
              Save
            </Button>
            <Button type="button" variant="ghost" onClick={() => setRenaming(false)}>
              Cancel
            </Button>
          </form>
        ) : (
          <div className={styles.quietRow}>
            <Button
              variant="ghost"
              onClick={() => {
                setNewName(room?.name ?? "");
                setRenaming(true);
              }}
            >
              Rename room
            </Button>
            <Button variant="ghost" onClick={handleDeleteRoom} className={styles.remove}>
              Remove room
            </Button>
          </div>
        )}
      </div>

      {showForm && (
        <TaskForm
          task={editing}
          rooms={rooms}
          defaultRoomId={roomId}
          onClose={closeForm}
        />
      )}
    </AppShell>
  );
}
