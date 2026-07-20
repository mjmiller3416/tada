"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import AuthGate from "@/components/AuthGate";
import { buildSession, completeTask, type Effort, type Task } from "@/lib/api";
import { roomTone } from "@/lib/decay";
import { Button, Card, Confetti, FocusCard } from "@/components/ui";
import styles from "./session.module.css";

/**
 * The focus session (SPEC §5) — the signature interaction. One task at a
 * time, a big Done and a quiet Skip, dots for momentum, and never the
 * full list. Launched from "I have X minutes" or by picking a room; both
 * arrive here as query params.
 */
export default function SessionPage() {
  return (
    <AuthGate>
      {() => (
        <Suspense fallback={null}>
          <SessionScreen />
        </Suspense>
      )}
    </AuthGate>
  );
}

type Phase = "loading" | "empty" | "active" | "complete";

function SessionScreen() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const minutesParam = searchParams.get("minutes");
  const roomParam = searchParams.get("room");
  const effortParam = searchParams.get("effort");

  const [phase, setPhase] = useState<Phase>("loading");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [index, setIndex] = useState(0);
  const [doneCount, setDoneCount] = useState(0);
  const [doneMinutes, setDoneMinutes] = useState(0);
  const [confetti, setConfetti] = useState(false);

  const build = useCallback(() => {
    setPhase("loading");
    setIndex(0);
    setDoneCount(0);
    setDoneMinutes(0);
    buildSession({
      minutes: minutesParam ? Number(minutesParam) : undefined,
      room_id: roomParam ? Number(roomParam) : undefined,
      effort:
        effortParam === "quick" || effortParam === "deep"
          ? (effortParam as Effort)
          : undefined,
    })
      .then((session) => {
        setTasks(session.tasks);
        setPhase(session.tasks.length > 0 ? "active" : "empty");
      })
      .catch(() => setPhase("empty"));
  }, [minutesParam, roomParam, effortParam]);

  useEffect(() => {
    build();
  }, [build]);

  function advance() {
    if (index + 1 >= tasks.length) {
      setPhase("complete");
      setConfetti(true);
    } else {
      setIndex(index + 1);
    }
  }

  function handleDone(task: Task) {
    // Log it, but never block her flow on the network — the card has
    // already celebrated.
    completeTask(task.id, "focus_session").catch(() => {});
    setDoneCount((n) => n + 1);
    setDoneMinutes((m) => m + task.estimated_minutes);
    advance();
  }

  const current = tasks[index];

  return (
    <main className={styles.page}>
      <Confetti active={confetti} onComplete={() => setConfetti(false)} />

      <header className={styles.topBar}>
        <Link href="/" className={styles.exit}>
          ✕ End session
        </Link>
      </header>

      <div className={styles.content}>
        {phase === "loading" && (
          <p className={styles.quiet}>Picking the right tasks…</p>
        )}

        {phase === "empty" && (
          <Card padding="lg" className={styles.endCard}>
            <p className={styles.bigEmoji}>🌤️</p>
            <h2 className={styles.endTitle}>Nothing needs you right now</h2>
            <p className={styles.endBody}>
              Everything here is feeling fresh. Enjoy the moment ✨
            </p>
            <Button variant="primary" size="lg" fullWidth onClick={() => router.push("/")}>
              Back home
            </Button>
          </Card>
        )}

        {phase === "active" && current && (
          <FocusCard
            key={current.id}
            taskName={current.name}
            estimatedMinutes={current.estimated_minutes}
            roomName={current.room_name ?? undefined}
            roomTone={roomTone(current.room_id)}
            current={index + 1}
            total={tasks.length}
            onDone={() => handleDone(current)}
            onSkip={advance}
          />
        )}

        {phase === "complete" && (
          <Card padding="lg" className={styles.endCard}>
            <p className={styles.bigEmoji}>🎉</p>
            <h2 className={styles.endTitle}>Ta-da! Session complete.</h2>
            <p className={styles.endBody}>
              {doneCount > 0
                ? `${doneCount} ${doneCount === 1 ? "task" : "tasks"} done — about ${doneMinutes} minutes of care. Your home says thank you.`
                : "You showed up, and that counts. Your home will be here when you’re ready."}
            </p>
            <Button variant="primary" size="lg" fullWidth onClick={() => router.push("/")}>
              Back home
            </Button>
            <Button variant="ghost" fullWidth onClick={build}>
              Keep going
            </Button>
          </Card>
        )}
      </div>
    </main>
  );
}
