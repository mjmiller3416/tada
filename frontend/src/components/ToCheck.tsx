"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import UndoToast from "@/components/UndoToast";
import {
  getChecks,
  markChecked,
  sendBack,
  trackWrite,
  undoCheck,
  type CheckItem,
} from "@/lib/api";
import { roomTone } from "@/lib/decay";
import { friendlyDate, toLocalDateValue } from "@/lib/dates";
import { Button, Card, Chip } from "@/components/ui";
import styles from "./ToCheck.module.css";

/** "3:40 PM" today, "Nov 12" on another day. */
function whenDone(iso: string): string {
  if (toLocalDateValue(iso) === toLocalDateValue()) {
    return new Date(iso).toLocaleTimeString(undefined, {
      hour: "numeric",
      minute: "2-digit",
    });
  }
  return friendlyDate(toLocalDateValue(iso));
}

/**
 * The parents' "To check" list (parent check): chores a kid finished on
 * a task that asks for a check. Small by nature and invisible when
 * empty. "Looks good" records that a parent looked; "Send back" makes
 * the chore due again, with an optional note the kid sees. Either one
 * offers the usual quiet Undo for a beat afterwards.
 *
 * `onChanged` lets the page refresh whatever else shows completions.
 */
export default function ToCheck({ onChanged }: { onChanged?: () => void }) {
  const [items, setItems] = useState<CheckItem[] | null>(null);
  const [sendingBackId, setSendingBackId] = useState<number | null>(null);
  const [note, setNote] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);
  // The Undo toast, keyed per action so its linger timer restarts.
  const [undoKey, setUndoKey] = useState<number | null>(null);
  const undoIdRef = useRef<number | null>(null);

  const load = useCallback(() => {
    getChecks()
      .then((r) => setItems(r.waiting))
      .catch(() => setItems([]));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function settle(item: CheckItem, action: Promise<CheckItem>) {
    setBusyId(item.completion_id);
    try {
      await trackWrite(action);
      setItems((current) =>
        current ? current.filter((c) => c.completion_id !== item.completion_id) : current,
      );
      undoIdRef.current = item.completion_id;
      setUndoKey((k) => (k ?? 0) + 1);
    } catch {
      load(); // show the honest state (someone else may have got there first)
    } finally {
      setBusyId(null);
      setSendingBackId(null);
      setNote("");
      onChanged?.();
    }
  }

  function handleUndo() {
    const completionId = undoIdRef.current;
    undoIdRef.current = null;
    if (completionId === null) return;
    trackWrite(undoCheck(completionId))
      .catch(() => {})
      .finally(() => {
        load();
        onChanged?.();
      });
  }

  if (items === null || (items.length === 0 && undoKey === null)) return null;

  return (
    <>
      {items.length > 0 && (
        <section id="to-check" aria-label="Ready for a check" className={styles.section}>
          <h2 className={styles.title}>Ready for a check 👀</h2>
          <p className={styles.hint}>
            Only tap “Looks good” once you’ve had a look yourself.
          </p>
          {items.map((item) => {
            const busy = busyId === item.completion_id;
            return (
              <Card key={item.completion_id} className={styles.card}>
                <div className={styles.top}>
                  <span className={styles.name}>{item.task_name}</span>
                  {item.room_name && (
                    <Chip tone={roomTone(item.room_id)}>{item.room_name}</Chip>
                  )}
                </div>
                <p className={styles.meta}>
                  {item.done_by_name} · done {whenDone(item.done_at)}
                </p>

                {sendingBackId === item.completion_id ? (
                  <div className={styles.sendBack}>
                    <label className={styles.noteLabel}>
                      What still needs doing? (optional)
                      <textarea
                        value={note}
                        onChange={(e) => setNote(e.target.value)}
                        rows={2}
                        maxLength={500}
                        className={styles.note}
                        placeholder="e.g. the mirror still has streaks"
                        autoFocus
                      />
                    </label>
                    <div className={styles.actions}>
                      <Button
                        variant="secondary"
                        onClick={() => settle(item, sendBack(item.completion_id, note))}
                        disabled={busy}
                      >
                        Send it back
                      </Button>
                      <Button
                        variant="ghost"
                        onClick={() => {
                          setSendingBackId(null);
                          setNote("");
                        }}
                        disabled={busy}
                      >
                        Never mind
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div className={styles.actions}>
                    <Button
                      variant="success"
                      onClick={() => settle(item, markChecked(item.completion_id))}
                      disabled={busy || busyId !== null}
                      className={styles.grow}
                    >
                      Looks good ✓
                    </Button>
                    <Button
                      variant="ghost"
                      onClick={() => {
                        setSendingBackId(item.completion_id);
                        setNote("");
                      }}
                      disabled={busy || busyId !== null}
                    >
                      Send back
                    </Button>
                  </div>
                )}
              </Card>
            );
          })}
        </section>
      )}

      {undoKey !== null && (
        <UndoToast key={undoKey} onUndo={handleUndo} onGone={() => setUndoKey(null)} />
      )}
    </>
  );
}
