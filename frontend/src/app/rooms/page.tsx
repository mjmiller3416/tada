"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import AuthGate from "@/components/AuthGate";
import { createRoom, getRooms, type Room } from "@/lib/api";
import { BAND_LABEL } from "@/lib/decay";
import { NAV_ITEMS } from "@/lib/nav";
import DirtinessDot from "@/components/DirtinessDot";
import { AppShell, Button, Card, Chip } from "@/components/ui";
import styles from "./rooms.module.css";

const MINUTE_CHOICES = [5, 15, 30, 45];

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
  // "Clean here" opens a quick time pick (Phase 4.6) — same chips as the
  // home screen, so a room session can be scoped to the time she has.
  const [timePickFor, setTimePickFor] = useState<number | null>(null);

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
            <div className={styles.roomTop}>
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
                  onClick={() =>
                    setTimePickFor(timePickFor === room.id ? null : room.id)
                  }
                >
                  Clean here
                </Button>
              )}
            </div>
            {timePickFor === room.id && (
              <div className={styles.timePick}>
                <span className={styles.timePickLabel}>
                  How much time do you have?
                </span>
                <div className={styles.timePickChips}>
                  {MINUTE_CHOICES.map((m) => (
                    <Chip
                      key={m}
                      tone="coral"
                      onClick={() =>
                        router.push(`/session?room=${room.id}&minutes=${m}`)
                      }
                    >
                      {m} min
                    </Chip>
                  ))}
                  <Chip
                    tone="neutral"
                    onClick={() => router.push(`/session?room=${room.id}`)}
                  >
                    The whole room
                  </Chip>
                </div>
              </div>
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
