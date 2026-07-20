"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import AuthGate from "@/components/AuthGate";
import DirtinessDot from "@/components/DirtinessDot";
import SnoozeMenu from "@/components/SnoozeMenu";
import {
  completeTask,
  getFocus,
  getSettings,
  snoozeTask,
  type Effort,
  type FocusResponse,
  type SnoozeOption,
  type Task,
} from "@/lib/api";
import { roomTone } from "@/lib/decay";
import { NAV_ITEMS } from "@/lib/nav";
import { AppShell, Burst, Button, Card, Chip } from "@/components/ui";
import styles from "./home.module.css";

const MINUTE_CHOICES = [5, 15, 30, 45];
const DONE_POP_MS = 650;

type EffortFilter = Effort | "all";

/**
 * The daily focus home screen (SPEC §6): a calm top-1..3, the "I have X
 * minutes" launcher, the energy filter, and decay-aware snooze. The
 * backlog lives one tap away in Rooms/Tasks — never here.
 */
export default function HomePage() {
  return (
    <AuthGate>
      {(user) => <HomeScreen firstName={user.name.split(" ")[0]} />}
    </AuthGate>
  );
}

function HomeScreen({ firstName }: { firstName: string }) {
  const router = useRouter();
  const [focus, setFocus] = useState<FocusResponse | null>(null);
  const [effort, setEffort] = useState<EffortFilter>("all");
  const [minutes, setMinutes] = useState(15);
  const [celebratingId, setCelebratingId] = useState<number | null>(null);
  const [snoozingId, setSnoozingId] = useState<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadFocus = useCallback((filter: EffortFilter) => {
    getFocus(filter === "all" ? undefined : filter)
      .then(setFocus)
      .catch(() => setFocus({ tasks: [], total_active_tasks: 0 }));
  }, []);

  useEffect(() => {
    loadFocus(effort);
  }, [effort, loadFocus]);

  useEffect(() => {
    getSettings()
      .then((s) => setMinutes(s.default_session_minutes))
      .catch(() => {});
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  function startSession() {
    const params = new URLSearchParams({ minutes: String(minutes) });
    if (effort !== "all") params.set("effort", effort);
    router.push(`/session?${params.toString()}`);
  }

  function handleDone(task: Task) {
    if (celebratingId !== null) return;
    setCelebratingId(task.id);
    timerRef.current = setTimeout(async () => {
      try {
        await completeTask(task.id, "direct");
      } finally {
        setCelebratingId(null);
        loadFocus(effort);
      }
    }, DONE_POP_MS);
  }

  async function handleSnooze(task: Task, option: Exclude<SnoozeOption, "wake">) {
    setSnoozingId(null);
    try {
      await snoozeTask(task.id, option);
    } finally {
      loadFocus(effort);
    }
  }

  const loading = focus === null;
  const needsSetup = focus !== null && focus.total_active_tasks === 0;
  const allCaughtUp = focus !== null && !needsSetup && focus.tasks.length === 0;

  return (
    <AppShell nav={NAV_ITEMS}>
      <header className={styles.greeting}>
        <h1 className={styles.hello}>Hi, {firstName} 👋</h1>
        <p className={styles.subline}>
          {needsSetup
            ? "Let’s get your home set up."
            : allCaughtUp
              ? "Your home feels good today. Enjoy it ✨"
              : "Here’s a gentle place to start."}
        </p>
      </header>

      {needsSetup ? (
        <Card padding="lg" className={styles.setupCard}>
          <p className={styles.setupEmoji}>🏡</p>
          <h2 className={styles.setupTitle}>Welcome to Tada!</h2>
          <p className={styles.setupBody}>
            Tell us about your rooms and we’ll build you a working schedule
            in a couple of minutes. Easiest on a bigger screen.
          </p>
          <Link href="/onboarding">
            <Button variant="primary" size="lg" fullWidth>
              Set up my home
            </Button>
          </Link>
        </Card>
      ) : (
        <>
          {/* ---- The "go" moment ---- */}
          <Card padding="lg" className={styles.heroCard}>
            <p className={styles.heroLabel}>How much time do you have?</p>
            <div className={styles.minuteRow}>
              {MINUTE_CHOICES.map((choice) => (
                <Chip
                  key={choice}
                  tone={minutes === choice ? "coral" : "neutral"}
                  onClick={() => setMinutes(choice)}
                >
                  {choice} min
                </Chip>
              ))}
            </div>
            <Button variant="primary" size="lg" fullWidth onClick={startSession}>
              I have {minutes} minutes
            </Button>
          </Card>

          {/* ---- Energy filter ---- */}
          <div className={styles.energyRow}>
            <Chip
              tone={effort === "all" ? "coral" : "neutral"}
              onClick={() => setEffort("all")}
            >
              Everything
            </Chip>
            <Chip
              tone={effort === "quick" ? "coral" : "neutral"}
              onClick={() => setEffort("quick")}
            >
              Quick wins
            </Chip>
            <Chip
              tone={effort === "deep" ? "coral" : "neutral"}
              onClick={() => setEffort("deep")}
            >
              Deep clean
            </Chip>
          </div>

          {/* ---- Today's focus ---- */}
          {!loading && !allCaughtUp && (
            <section className={styles.focusList} aria-label="Today's focus">
              {focus.tasks.map((task) => (
                <Card key={task.id} className={styles.taskCard}>
                  <div className={styles.taskTop}>
                    <DirtinessDot band={task.band} />
                    <span className={styles.taskName}>{task.name}</span>
                    {task.room_name && (
                      <Chip tone={roomTone(task.room_id)}>{task.room_name}</Chip>
                    )}
                  </div>
                  <p className={styles.taskMeta}>about {task.estimated_minutes} min</p>

                  {snoozingId === task.id ? (
                    <SnoozeMenu
                      onPick={(option) => handleSnooze(task, option)}
                      onCancel={() => setSnoozingId(null)}
                    />
                  ) : (
                    <div className={styles.taskActions}>
                      <span className={styles.burstAnchor}>
                        <Burst play={celebratingId === task.id} />
                        <Button
                          variant="success"
                          onClick={() => handleDone(task)}
                          disabled={celebratingId !== null}
                        >
                          Done!
                        </Button>
                      </span>
                      <Button
                        variant="ghost"
                        onClick={() => setSnoozingId(task.id)}
                        disabled={celebratingId !== null}
                      >
                        Later
                      </Button>
                    </div>
                  )}
                </Card>
              ))}
            </section>
          )}

          {allCaughtUp && (
            <Card padding="lg" className={styles.caughtUpCard}>
              <p className={styles.setupEmoji}>🌤️</p>
              <p className={styles.caughtUpText}>
                Nothing needs you right now. If you’re in the mood anyway,
                pick a room and give it some love.
              </p>
              <Link href="/rooms">
                <Button variant="secondary" fullWidth>
                  Browse rooms
                </Button>
              </Link>
            </Card>
          )}
        </>
      )}
    </AppShell>
  );
}
