"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import AuthGate from "@/components/AuthGate";
import { createRoom, getRooms, type Room } from "@/lib/api";
import { BAND_LABEL } from "@/lib/decay";
import { NAV_ITEMS } from "@/lib/nav";
import DirtinessDot from "@/components/DirtinessDot";
import { AppShell, Button, Card } from "@/components/ui";
import styles from "./rooms.module.css";

/**
 * The Room view (SPEC §6): every room with its aggregate dirtiness — a
 * planning surface. Tapping a room opens its detail; "Clean here" jumps
 * straight into a room-scoped focus session.
 */
export default function RoomsPage() {
  return <AuthGate ownerOnly>{() => <RoomsScreen />}</AuthGate>;
}

function RoomsScreen() {
  const router = useRouter();
  const [rooms, setRooms] = useState<Room[] | null>(null);
  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    getRooms()
      .then(setRooms)
      .catch(() => setRooms([]));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim() || saving) return;
    setSaving(true);
    try {
      await createRoom(newName.trim());
      setNewName("");
      setAdding(false);
      load();
    } finally {
      setSaving(false);
    }
  }

  return (
    <AppShell title="Rooms" nav={NAV_ITEMS}>
      {rooms !== null && rooms.length === 0 && (
        <Card padding="lg" className={styles.emptyCard}>
          <p className={styles.emptyEmoji}>🏡</p>
          <p className={styles.emptyText}>
            No rooms yet — the setup wizard builds them (with a starter
            schedule) in a couple of minutes.
          </p>
          <Link href="/onboarding">
            <Button variant="primary" fullWidth>
              Set up my home
            </Button>
          </Link>
        </Card>
      )}

      <div className={styles.list}>
        {rooms?.map((room) => (
          <Card key={room.id} className={styles.roomCard}>
            <button
              type="button"
              className={styles.roomMain}
              onClick={() => router.push(`/rooms/${room.id}`)}
            >
              <span className={styles.roomName}>{room.name}</span>
              <span className={styles.roomMeta}>
                {room.band ? (
                  <>
                    <DirtinessDot band={room.band} withLabel />
                    {room.due_count > 0 && (
                      <span className={styles.dueNote}>
                        · {room.due_count} ready for attention
                      </span>
                    )}
                  </>
                ) : (
                  <span className={styles.dueNote}>No tasks yet</span>
                )}
              </span>
            </button>
            {room.due_count > 0 && (
              <Button
                variant="primary"
                onClick={() => router.push(`/session?room=${room.id}`)}
              >
                Clean here
              </Button>
            )}
          </Card>
        ))}
      </div>

      {adding ? (
        <form onSubmit={handleAdd} className={styles.addForm}>
          <input
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="Room name"
            className={styles.input}
            autoFocus
          />
          <Button type="submit" variant="primary" disabled={!newName.trim() || saving}>
            Add
          </Button>
          <Button type="button" variant="ghost" onClick={() => setAdding(false)}>
            Cancel
          </Button>
        </form>
      ) : (
        rooms !== null &&
        rooms.length > 0 && (
          <Button variant="secondary" fullWidth onClick={() => setAdding(true)}>
            + Add a room
          </Button>
        )
      )}
    </AppShell>
  );
}
