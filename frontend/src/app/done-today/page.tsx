"use client";

import { useCallback, useEffect, useState } from "react";
import AuthGate from "@/components/AuthGate";
import {
  afterPendingWrites,
  getDoneToday,
  trackWrite,
  undoCompletion,
  type DoneTodayEntry,
  type DoneTodayResponse,
} from "@/lib/api";
import { roomTone } from "@/lib/decay";
import { NAV_ITEMS } from "@/lib/nav";
import { AppShell, Card, Chip } from "@/components/ui";
import styles from "./done-today.module.css";

/** Badge ids she has already seen, kept per device so anything earned
 * since her last visit gets a little "New!" moment. */
const SEEN_BADGES_KEY = "tada-seen-badges";

function readSeenBadges(): Set<number> {
  try {
    const raw = localStorage.getItem(SEEN_BADGES_KEY);
    return new Set(raw ? (JSON.parse(raw) as number[]) : []);
  } catch {
    return new Set();
  }
}

/**
 * The Done Today view (Phase 5): everything finished today, her streak,
 * and the badges she's earned — read straight from the CompletionLog.
 *
 * Accumulation ONLY, by design: no denominators, no percentages, no
 * targets, nothing comparative. It shows what she did, full stop —
 * a reward, never a scoreboard.
 */
export default function DoneTodayPage() {
  return <AuthGate ownerOnly>{() => <DoneTodayScreen />}</AuthGate>;
}

function DoneTodayScreen() {
  const [data, setData] = useState<DoneTodayResponse | null>(null);
  const [newBadgeIds, setNewBadgeIds] = useState<Set<number>>(new Set());

  const load = useCallback(() => {
    // Order behind in-flight Done/Undo posts — arriving here straight
    // from a session must show every ta-da that's still on the wire.
    afterPendingWrites()
      .then(() => getDoneToday())
      .then((response) => {
        const seen = readSeenBadges();
        setNewBadgeIds(
          new Set(
            response.badges.filter((b) => !seen.has(b.id)).map((b) => b.id),
          ),
        );
        // Mark everything seen for next time — the sparkle is a one-visit
        // moment, not a persistent nag.
        try {
          localStorage.setItem(
            SEEN_BADGES_KEY,
            JSON.stringify(response.badges.map((b) => b.id)),
          );
        } catch {
          // Storage full/blocked — the highlight just shows again later.
        }
        setData(response);
      })
      .catch(() =>
        setData({
          date: "",
          completions: [],
          streak: 0,
          badges: [],
          household_members: 1,
        }),
      );
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  /** Undo one completion (Phase 9): the row leaves the list; the streak
   * display is deliberately untouched — streaks only ever go up. If it
   * was the only one, the normal warm empty state simply returns, with
   * no mention of the undo. */
  function handleUndo(entry: DoneTodayEntry) {
    setData(
      (current) =>
        current && {
          ...current,
          completions: current.completions.filter((c) => c.id !== entry.id),
        },
    );
    // Quietly resync if the server disagrees (e.g. the day rolled over).
    // Tracked, so the home screen she returns to orders behind it.
    trackWrite(undoCompletion(entry.id)).catch(() => load());
  }

  function timeOf(iso: string): string {
    return new Date(iso).toLocaleTimeString(undefined, {
      hour: "numeric",
      minute: "2-digit",
    });
  }

  return (
    <AppShell title="Done today" nav={NAV_ITEMS}>
      {data === null ? (
        <p className={styles.quiet}>Gathering today’s ta-das…</p>
      ) : (
        <>
          {/* ---- The streak, shown warmly. Just the current number —
               a broken streak is never announced or explained. ---- */}
          {data.streak > 0 && (
            <Card className={styles.streakCard}>
              <span className={styles.streakFlame} aria-hidden="true">
                🔥
              </span>
              <div>
                <p className={styles.streakCount}>
                  {data.streak}-day streak
                </p>
                <p className={styles.streakNote}>
                  Showing up counts — look at you go.
                </p>
              </div>
            </Card>
          )}

          {/* ---- Today's completions ---- */}
          {data.completions.length === 0 ? (
            <Card padding="lg" className={styles.emptyCard}>
              <p className={styles.emptyEmoji}>🌅</p>
              <p className={styles.emptyText}>
                Nothing logged yet today — the day’s still young ✨
              </p>
            </Card>
          ) : (
            <section aria-label="Finished today" className={styles.doneList}>
              <h2 className={styles.sectionTitle}>
                {data.completions.length}{" "}
                {data.completions.length === 1 ? "ta-da" : "ta-das"} today
              </h2>
              {data.completions.map((entry) => (
                <Card key={entry.id} className={styles.doneCard}>
                  <span className={styles.doneCheck} aria-hidden="true">
                    ✓
                  </span>
                  <div className={styles.doneBody}>
                    <p className={styles.doneName}>{entry.task_name}</p>
                    <p className={styles.doneMeta}>
                      {timeOf(entry.completed_at)}
                      {data.household_members > 1 &&
                        ` · ${entry.completed_by_name}`}
                    </p>
                  </div>
                  {entry.room_name && (
                    <Chip tone={roomTone(entry.room_id)}>{entry.room_name}</Chip>
                  )}
                  {/* Small and secondary on purpose — a safety net,
                      never a button competing with the content. */}
                  <button
                    type="button"
                    className={styles.undoLink}
                    onClick={() => handleUndo(entry)}
                    aria-label={`Undo ${entry.task_name}`}
                  >
                    Undo
                  </button>
                </Card>
              ))}
            </section>
          )}

          {/* ---- Earned badges (only ever the earned ones) ---- */}
          {data.badges.length > 0 && (
            <section aria-label="Badges" className={styles.badgeSection}>
              <h2 className={styles.sectionTitle}>Your badges</h2>
              <div className={styles.badgeGrid}>
                {data.badges.map((badge) => (
                  <Card key={badge.id} className={styles.badgeCard}>
                    {newBadgeIds.has(badge.id) && (
                      <span className={styles.badgeNew}>New!</span>
                    )}
                    <span className={styles.badgeEmoji} aria-hidden="true">
                      {badge.emoji}
                    </span>
                    <p className={styles.badgeName}>{badge.name}</p>
                    <p className={styles.badgeDesc}>{badge.description}</p>
                  </Card>
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </AppShell>
  );
}
