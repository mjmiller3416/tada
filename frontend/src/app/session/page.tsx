"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import AuthGate from "@/components/AuthGate";
import UndoToast from "@/components/UndoToast";
import {
  afterPendingWrites,
  buildSession,
  cancelSessionTimer,
  completeSession,
  completeTask,
  extendSessionTimer,
  startSessionTimer,
  trackWrite,
  undoCompletion,
  type Badge,
  type CompleteResponse,
  type CompletionSource,
  type Effort,
  type SessionTimer,
  type Task,
} from "@/lib/api";
import { roomTone } from "@/lib/decay";
import { supplyNote } from "@/lib/supplies";
import { Button, Card, Confetti, FocusCard } from "@/components/ui";
import styles from "./session.module.css";

/** How much a "+10 min" tap adds — time and tasks both. */
const EXTEND_MINUTES = 10;

/**
 * The focus session (SPEC §5) — the signature interaction. One task at a
 * time, a big Done and a quiet Skip, dots for momentum, and never the
 * full list. Launched from "I have X minutes", a room, or — Phase 3 —
 * guest/Chaos mode, this week's zone, or a campaign; all arrive here as
 * query params and run through the exact same one-card flow.
 *
 * Phase 5 adds the optional timer (a real push via the Reminder + cron
 * plumbing, so it survives a pocketed phone) and the session-complete
 * badge check behind the celebration.
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
    // Zone sessions launch from "this week's zone" AND (Phase 4.6) the
    // home time-box with any zone picked — so the tag names no week.
    tag: "🧭 Zone focus",
    source: "zone",
    emptyTitle: "This zone is feeling fresh",
    emptyBody: "It's in lovely shape — nothing needs you here ✨",
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
  // Phase 11: a mission-only zone session ("this week's zone"). The
  // backend ignores it while the lanes are off, so this link degrades
  // gracefully to the legacy zone session.
  const isMissions = searchParams.get("missions") === "1";
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

  // The optional timer (Phase 5). Lives on the backend as a Reminder so
  // the "time's up" push arrives even with the screen asleep. It never
  // ends the session — she decides when she's done.
  const [timer, setTimer] = useState<SessionTimer | null>(null);
  const [timerBusy, setTimerBusy] = useState(false);

  // Badges surfaced by the session-complete check (SPEC §5: celebration
  // + badge check). Earned mid-session ones ride along via started_at.
  const [newBadges, setNewBadges] = useState<Badge[]>([]);
  const startedAtRef = useRef<string>(new Date().toISOString());
  // Completions post fire-and-forget so Done never blocks on the
  // network; the complete-check waits for them so no badge shows late.
  const pendingCompletionsRef = useRef<Promise<unknown>[]>([]);

  // Skip is presentation only — it never logs, snoozes, or touches
  // last_done_at — so a rebuild ("Keep going") returns the same ranking
  // with the skipped task legitimately still on top. Remembering what
  // she skipped lets us serve fresh tasks first without ever telling
  // the decay engine about it.
  const skippedIdsRef = useRef<Set<number>>(new Set());

  // The Undo toast (Phase 9): always for the most recent Done. Keyed so
  // each completion restarts the toast's linger; the ref carries the
  // in-flight completion post whose id an undo would need, plus the
  // task itself so an undo can put it straight back in the queue.
  const [undoKey, setUndoKey] = useState<number | null>(null);
  const lastCompletionRef = useRef<{
    post: Promise<CompleteResponse | null>;
    task: Task;
  } | null>(null);

  const build = useCallback(() => {
    setPhase("loading");
    setIndex(0);
    setDoneCount(0);
    setDoneMinutes(0);
    setNewBadges([]);
    startedAtRef.current = new Date().toISOString();
    // Order behind any in-flight Done/Undo posts, so "Keep going" never
    // rebuilds from a ranking the server hasn't caught up to yet.
    afterPendingWrites()
      .then(() =>
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
          zone_missions: isMissions || undefined,
        }),
      )
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
  }, [minutesParam, roomParam, effortParam, zoneParam, campaignParam, isGuest, isMissions]);

  useEffect(() => {
    build();
  }, [build]);

  // The session-complete badge check, once per completed run. Waits for
  // any in-flight completion posts so the last Done's badge isn't missed.
  useEffect(() => {
    if (phase !== "complete") return;
    const pending = pendingCompletionsRef.current;
    pendingCompletionsRef.current = [];
    Promise.allSettled(pending)
      .then(() =>
        completeSession({
          tasks_done: doneCount,
          started_at: startedAtRef.current,
        }),
      )
      .then((result) => setNewBadges(result.new_badges))
      .catch(() => {});
    // doneCount is settled by the time phase flips to complete.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase]);

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
    // already celebrated. Tracked, so any surface that reads task state
    // next (home, a rebuild) orders behind it.
    const post = trackWrite(completeTask(task.id, copy.source)).catch(
      () => null,
    );
    pendingCompletionsRef.current.push(post);
    // Offer Undo for a beat (Phase 9) — except in guest mode, which
    // stays deliberately minimal for a houseguest.
    if (mode !== "guest") {
      lastCompletionRef.current = { post, task };
      setUndoKey((k) => (k ?? 0) + 1);
    }
    skippedIdsRef.current.delete(task.id);
    setDoneCount((n) => n + 1);
    setDoneMinutes((m) => m + task.estimated_minutes);
    advance();
  }

  function handleUndo() {
    const last = lastCompletionRef.current;
    lastCompletionRef.current = null;
    if (!last) return;
    // Fire-and-forget, like the completion itself — undo never holds
    // her up either. Tracked as ONE chain (completion post, then the
    // undo), so a home-screen fetch right after can't slip in between
    // and render the pre-undo world. If the completion post failed,
    // there is nothing on the server to reverse.
    trackWrite(
      last.post.then((done) =>
        done ? undoCompletion(done.completion_id).catch(() => {}) : undefined,
      ),
    );
    // Keep the session's own numbers honest.
    setDoneCount((n) => Math.max(0, n - 1));
    setDoneMinutes((m) => Math.max(0, m - last.task.estimated_minutes));
    // She didn't actually do it — put it back at the end of the queue
    // so it returns live, without interrupting the current card. On the
    // complete screen the session stays finished; the task resurfaces
    // on the home screen instead.
    if (phase === "active") {
      setTasks((current) =>
        current.some((t) => t.id === last.task.id)
          ? current
          : [...current, last.task],
      );
    }
  }

  function handleSkip(task: Task) {
    skippedIdsRef.current.add(task.id);
    advance();
  }

  async function handleStartTimer() {
    if (!minutesParam || timerBusy) return;
    setTimerBusy(true);
    try {
      setTimer(await startSessionTimer(Number(minutesParam)));
    } catch {
      // No timer is just a session without a nudge — nothing to say.
    } finally {
      setTimerBusy(false);
    }
  }

  async function handleExtendTimer() {
    if (!timer || timerBusy) return;
    setTimerBusy(true);
    try {
      // More time AND more to do with it — extending must never leave
      // her with minutes and an empty queue.
      const extended = await extendSessionTimer(timer.id, EXTEND_MINUTES);
      setTimer(extended);
      const topUp = await buildSession({
        minutes: EXTEND_MINUTES,
        room_id: roomParam ? Number(roomParam) : undefined,
        effort:
          effortParam === "quick" || effortParam === "deep"
            ? (effortParam as Effort)
            : undefined,
        zone_id: zoneParam ? Number(zoneParam) : undefined,
        guest: isGuest || undefined,
        zone_missions: isMissions || undefined,
        exclude_task_ids: tasks.map((t) => t.id),
      });
      const queued = new Set(tasks.map((t) => t.id));
      const additions = topUp.tasks.filter((t) => !queued.has(t.id));
      if (additions.length > 0) {
        setTasks((current) => [...current, ...additions]);
      }
    } catch {
      // The extra time still stands if the top-up fetch hiccuped.
    } finally {
      setTimerBusy(false);
    }
  }

  /** Leaving the session takes any pending timer alert with it. */
  function dropTimer() {
    if (timer) {
      cancelSessionTimer(timer.id).catch(() => {});
      setTimer(null);
    }
  }

  function goHome() {
    dropTimer();
    router.push("/");
  }

  function timerLabel(): string {
    const at = new Date(timer!.fires_at);
    return at.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
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

      {/* Undo for the last Done (Phase 9). An overlay, never a gate —
          the next card is already up and she can keep going past it. */}
      {undoKey !== null && (
        <UndoToast
          key={undoKey}
          onUndo={handleUndo}
          onGone={() => setUndoKey(null)}
        />
      )}

      <header className={styles.topBar}>
        {copy.tag && (
          <span className={styles.modeTag}>
            {copy.tag}
            {label ? ` · ${label}` : ""}
          </span>
        )}
        <Link href="/" className={styles.exit} onClick={dropTimer}>
          ✕ End session
        </Link>
      </header>

      {/* ---- Optional timer for timed sessions (Phase 5) ---- */}
      {phase === "active" && minutesParam && (
        <div className={styles.timerRow}>
          {timer === null ? (
            <button
              type="button"
              className={styles.timerLink}
              onClick={handleStartTimer}
              disabled={timerBusy}
            >
              🔔 Nudge me when my {minutesParam} minutes are up
            </button>
          ) : (
            <>
              <span className={styles.timerStatus}>
                🔔 We’ll nudge you around {timerLabel()}
              </span>
              <button
                type="button"
                className={styles.timerLink}
                onClick={handleExtendTimer}
                disabled={timerBusy}
              >
                +{EXTEND_MINUTES} min
              </button>
            </>
          )}
        </div>
      )}

      <div className={styles.content}>
        {phase === "loading" && (
          <p className={styles.quiet}>Picking the right tasks…</p>
        )}

        {phase === "empty" && (
          <Card padding="lg" className={styles.endCard}>
            <p className={styles.bigEmoji}>🌤️</p>
            <h2 className={styles.endTitle}>{copy.emptyTitle}</h2>
            <p className={styles.endBody}>{copy.emptyBody}</p>
            <Button variant="primary" size="lg" fullWidth onClick={goHome}>
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
            // The one composed mission in a timed/room session carries
            // its zone label (Phase 11). Zone sessions already say so in
            // the header tag, so no per-card repeat there.
            missionLabel={
              mode !== "zone" && current.task_type === "zone" && current.zone_name
                ? `🧭 This week’s ${current.zone_name} mission`
                : undefined
            }
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
            <Button variant="primary" size="lg" fullWidth onClick={goHome}>
              Back home
            </Button>
          </Card>
        )}

        {phase === "complete" && (
          <Card padding="lg" className={styles.endCard}>
            <p className={styles.bigEmoji}>🎉</p>
            <h2 className={styles.endTitle}>Ta-da! Session complete.</h2>
            <p className={styles.endBody}>{completeBody}</p>

            {/* Freshly earned badges — little gifts, shown right in the
                celebration (SPEC §5's badge check). */}
            {newBadges.map((badge) => (
              <div key={badge.id} className={styles.badgeEarned}>
                <span className={styles.badgeEarnedEmoji} aria-hidden="true">
                  {badge.emoji}
                </span>
                <div className={styles.badgeEarnedBody}>
                  <p className={styles.badgeEarnedName}>
                    New badge: {badge.name}
                  </p>
                  <p className={styles.badgeEarnedDesc}>{badge.description}</p>
                </div>
              </div>
            ))}

            <Button variant="primary" size="lg" fullWidth onClick={goHome}>
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
