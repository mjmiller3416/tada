"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import AuthGate from "@/components/AuthGate";
import {
  buildSession,
  completeTask,
  type CompletionSource,
  type Effort,
  type Task,
} from "@/lib/api";
import { roomTone } from "@/lib/decay";
import { supplyNote } from "@/lib/supplies";
import { Button, Card, Confetti, FocusCard } from "@/components/ui";
import styles from "./session.module.css";

/**
 * The focus session (SPEC §5) — the signature interaction. One task at a
 * time, a big Done and a quiet Skip, dots for momentum, and never the
 * full list. Launched from "I have X minutes", a room, or — Phase 3 —
 * guest/Chaos mode, this week's zone, or a campaign; all arrive here as
 * query params and run through the exact same one-card flow.
 */
export default function SessionPage() {
  return (
    <AuthGate ownerOnly>
      {() => (
        <Suspense fallback={null}>
          <SessionScreen />
        </Suspense>
      )}
    </AuthGate>
  );
}

type Phase = "loading" | "empty" | "active" | "complete" | "allSkipped";

type Mode = "focus" | "guest" | "zone" | "campaign";

/** Per-mode flavor: the little header tag, the completion source that
 * lands in history, and warm mode-specific copy. */
const MODE_COPY: Record<
  Mode,
  { tag: string | null; source: CompletionSource; emptyTitle: string; emptyBody: string }
> = {
  focus: {
    tag: null,
    source: "focus_session",
    emptyTitle: "Nothing needs you right now",
    emptyBody: "Everything here is feeling fresh. Enjoy the moment ✨",
  },
  guest: {
    tag: "🚪 Chaos clean — quick, visible wins",
    source: "guest_mode",
    emptyTitle: "The guest spots look great",
    emptyBody: "Truly — you're ready for company. Go put the kettle on ☕",
  },
  zone: {
    tag: "🧭 This week's zone",
    source: "zone",
    emptyTitle: "This zone is feeling fresh",
    emptyBody: "Its week is going beautifully. Nothing needs you here ✨",
  },
  campaign: {
    tag: "🌷 Campaign",
    source: "campaign",
    emptyTitle: "That's the whole campaign!",
    emptyBody: "Every single task, done. What a finish 🎉",
  },
};

function SessionScreen() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const minutesParam = searchParams.get("minutes");
  const roomParam = searchParams.get("room");
  const effortParam = searchParams.get("effort");
  const zoneParam = searchParams.get("zone");
  const campaignParam = searchParams.get("campaign");
  const isGuest = searchParams.get("guest") === "1";
  const label = searchParams.get("label");

  const mode: Mode = campaignParam
    ? "campaign"
    : zoneParam
      ? "zone"
      : isGuest
        ? "guest"
        : "focus";
  const copy = MODE_COPY[mode];

  const [phase, setPhase] = useState<Phase>("loading");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [index, setIndex] = useState(0);
  const [doneCount, setDoneCount] = useState(0);
  const [doneMinutes, setDoneMinutes] = useState(0);
  const [confetti, setConfetti] = useState(false);

  // Skip is presentation only — it never logs, snoozes, or touches
  // last_done_at — so a rebuild ("Keep going") returns the same ranking
  // with the skipped task legitimately still on top. Remembering what
  // she skipped lets us serve fresh tasks first without ever telling
  // the decay engine about it.
  const skippedIdsRef = useRef<Set<number>>(new Set());

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
      zone_id: zoneParam ? Number(zoneParam) : undefined,
      campaign_id: campaignParam ? Number(campaignParam) : undefined,
      guest: isGuest || undefined,
    })
      .then((session) => {
        const skipped = skippedIdsRef.current;
        const fresh = session.tasks.filter((task) => !skipped.has(task.id));
        const deferred = session.tasks.filter((task) => skipped.has(task.id));
        if (session.tasks.length === 0) {
          setPhase("empty");
        } else if (fresh.length === 0) {
          // Everything left is something she already skipped — don't
          // loop her through it again.
          setPhase("allSkipped");
        } else {
          setTasks([...fresh, ...deferred]);
          setPhase("active");
        }
      })
      .catch(() => setPhase("empty"));
  }, [minutesParam, roomParam, effortParam, zoneParam, campaignParam, isGuest]);

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
    completeTask(task.id, copy.source).catch(() => {});
    skippedIdsRef.current.delete(task.id);
    setDoneCount((n) => n + 1);
    setDoneMinutes((m) => m + task.estimated_minutes);
    advance();
  }

  function handleSkip(task: Task) {
    skippedIdsRef.current.add(task.id);
    advance();
  }

  const current = tasks[index];

  const completeBody =
    doneCount === 0
      ? "You showed up, and that counts. Your home will be here when you’re ready."
      : mode === "guest"
        ? `${doneCount} ${doneCount === 1 ? "spot" : "spots"} guest-ready in about ${doneMinutes} minutes. Let them ring the bell 🛎️`
        : mode === "campaign"
          ? `${doneCount} more ${doneCount === 1 ? "task" : "tasks"} toward the finish line. Lovely, steady progress 🌷`
          : `${doneCount} ${doneCount === 1 ? "task" : "tasks"} done — about ${doneMinutes} minutes of care. Your home says thank you.`;

  return (
    <main className={styles.page}>
      <Confetti active={confetti} onComplete={() => setConfetti(false)} />

      <header className={styles.topBar}>
        {copy.tag && (
          <span className={styles.modeTag}>
            {copy.tag}
            {label ? ` · ${label}` : ""}
          </span>
        )}
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
            <h2 className={styles.endTitle}>{copy.emptyTitle}</h2>
            <p className={styles.endBody}>{copy.emptyBody}</p>
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
            supplyNote={supplyNote(current) ?? undefined}
            current={index + 1}
            total={tasks.length}
            onDone={() => handleDone(current)}
            onSkip={() => handleSkip(current)}
          />
        )}

        {phase === "allSkipped" && (
          <Card padding="lg" className={styles.endCard}>
            <p className={styles.bigEmoji}>🌙</p>
            <h2 className={styles.endTitle}>The rest can wait</h2>
            <p className={styles.endBody}>
              Everything left is something you set aside — and “not now” is
              a perfectly good answer. It’ll all be here when you’re ready 💛
            </p>
            <Button variant="primary" size="lg" fullWidth onClick={() => router.push("/")}>
              Back home
            </Button>
          </Card>
        )}

        {phase === "complete" && (
          <Card padding="lg" className={styles.endCard}>
            <p className={styles.bigEmoji}>🎉</p>
            <h2 className={styles.endTitle}>Ta-da! Session complete.</h2>
            <p className={styles.endBody}>{completeBody}</p>
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
