"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  claimTask,
  completeTask,
  getChores,
  logout,
  type ChoresResponse,
  type Task,
} from "@/lib/api";
import { roomTone } from "@/lib/decay";
import { AppShell, Burst, Button, Card, Chip, Confetti } from "@/components/ui";
import styles from "./KidHome.module.css";

const DONE_POP_MS = 650;

/**
 * The whole kid experience (SPEC §6 multi-user): their chores and what's
 * up for grabs, one big Done per chore, and nothing else — no points, no
 * levels, no pressure. Completing notifies the owner on the backend.
 */
export default function KidHome({ firstName }: { firstName: string }) {
  const router = useRouter();
  const [chores, setChores] = useState<ChoresResponse | null>(null);
  const [celebratingId, setCelebratingId] = useState<number | null>(null);
  const [claimingId, setClaimingId] = useState<number | null>(null);
  const [confetti, setConfetti] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(() => {
    getChores()
      .then(setChores)
      .catch(() => setChores({ mine: [], up_for_grabs: [] }));
  }, []);

  useEffect(() => {
    load();
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [load]);

  function handleDone(task: Task) {
    if (celebratingId !== null) return;
    setCelebratingId(task.id);
    // The write fires NOW (issue #11): a kid tapping Done then Log out
    // within the pop must still get their chore counted — the timer
    // only paces the celebration and the reload.
    const post = completeTask(task.id, "direct").catch(() => null);
    timerRef.current = setTimeout(async () => {
      await post;
      setCelebratingId(null);
      // A finished list deserves a bigger cheer than a single pop.
      if (chores && chores.mine.length === 1 && task.assignee_id !== null) {
        setConfetti(true);
      }
      load();
    }, DONE_POP_MS);
  }

  async function handleClaim(task: Task) {
    setClaimingId(task.id);
    try {
      await claimTask(task.id);
    } finally {
      setClaimingId(null);
      load();
    }
  }

  async function handleLogout() {
    await logout().catch(() => {});
    router.replace("/login");
  }

  const loading = chores === null;
  const nothingToDo =
    chores !== null && chores.mine.length === 0 && chores.up_for_grabs.length === 0;

  return (
    <AppShell>
      <Confetti active={confetti} onComplete={() => setConfetti(false)} />

      <header className={styles.greeting}>
        <h1 className={styles.hello}>Hi, {firstName} 👋</h1>
        <p className={styles.subline}>
          {nothingToDo
            ? "No chores right now — enjoy it! 🎉"
            : "Here’s what would really help today."}
        </p>
      </header>

      {!loading && chores.mine.length > 0 && (
        <section className={styles.section} aria-label="Your chores">
          <h2 className={styles.sectionTitle}>Your chores</h2>
          {chores.mine.map((task) => (
            <ChoreCard
              key={task.id}
              task={task}
              celebrating={celebratingId === task.id}
              busy={celebratingId !== null}
              onDone={() => handleDone(task)}
            />
          ))}
        </section>
      )}

      {!loading && chores.up_for_grabs.length > 0 && (
        <section className={styles.section} aria-label="Up for grabs">
          <h2 className={styles.sectionTitle}>Up for grabs</h2>
          <p className={styles.sectionHint}>
            Nobody’s on these yet — tap one to make it yours.
          </p>
          {chores.up_for_grabs.map((task) => (
            <ChoreCard
              key={task.id}
              task={task}
              celebrating={celebratingId === task.id}
              busy={celebratingId !== null || claimingId !== null}
              onDone={() => handleDone(task)}
              onClaim={() => handleClaim(task)}
              claiming={claimingId === task.id}
            />
          ))}
        </section>
      )}

      {nothingToDo && (
        <Card padding="lg" className={styles.emptyCard}>
          <p className={styles.emptyEmoji}>🌟</p>
          <p className={styles.emptyText}>
            All clear! Check back later — something might open up.
          </p>
        </Card>
      )}

      <Button variant="ghost" fullWidth onClick={handleLogout} className={styles.logout}>
        Log out
      </Button>
    </AppShell>
  );
}

function ChoreCard({
  task,
  celebrating,
  busy,
  claiming = false,
  onDone,
  onClaim,
}: {
  task: Task;
  celebrating: boolean;
  busy: boolean;
  claiming?: boolean;
  onDone: () => void;
  onClaim?: () => void;
}) {
  return (
    <Card className={styles.choreCard}>
      <div className={styles.choreTop}>
        <span className={styles.choreName}>{task.name}</span>
        {task.room_name && (
          <Chip tone={roomTone(task.room_id)}>{task.room_name}</Chip>
        )}
      </div>
      <p className={styles.choreMeta}>about {task.estimated_minutes} min</p>
      <div className={styles.choreActions}>
        <span className={styles.burstAnchor}>
          <Burst play={celebrating} />
          <Button variant="success" onClick={onDone} disabled={busy}>
            Done!
          </Button>
        </span>
        {onClaim && (
          <Button variant="secondary" onClick={onClaim} disabled={busy}>
            {claiming ? "One sec…" : "I’ll do it!"}
          </Button>
        )}
      </div>
    </Card>
  );
}
