"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import AuthGate from "@/components/AuthGate";
import DirtinessDot from "@/components/DirtinessDot";
import KidHome from "@/components/KidHome";
import SnoozeMenu from "@/components/SnoozeMenu";
import UndoToast from "@/components/UndoToast";
import {
  afterPendingWrites,
  completeTask,
  getCampaigns,
  getFocus,
  getSettings,
  getZones,
  snoozeTask,
  trackWrite,
  undoCompletion,
  updateSettings,
  type Campaign,
  type Effort,
  type FocusResponse,
  type SnoozeOption,
  type Task,
  type Zone,
} from "@/lib/api";
import { roomTone, snoozedLabel } from "@/lib/decay";
import { friendlyDate, toLocalDateValue } from "@/lib/dates";
import { supplyNote } from "@/lib/supplies";
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
 *
 * Kids land here too, but get their own small surface (Phase 2): just
 * their chores and what's up for grabs.
 */
export default function HomePage() {
  return (
    <AuthGate>
      {(user) =>
        user.role === "kid" ? (
          <KidHome firstName={user.name.split(" ")[0]} />
        ) : (
          <HomeScreen firstName={user.name.split(" ")[0]} />
        )
      }
    </AuthGate>
  );
}

function HomeScreen({ firstName }: { firstName: string }) {
  const router = useRouter();
  const [focus, setFocus] = useState<FocusResponse | null>(null);
  const [effort, setEffort] = useState<EffortFilter>("all");
  const [minutes, setMinutes] = useState(15);
  const [currentZone, setCurrentZone] = useState<Zone | null>(null);
  // The optional zone scope for "I have X minutes" (Phase 4.6). Only
  // offered when the zones overlay is on — never a dead control. With
  // the Phase 11 lanes on, picking a zone means that zone's rooms plus
  // its missions — the backend composes it; the request is the same.
  const [zones, setZones] = useState<Zone[]>([]);
  // Phase 11: whether the scheduling lanes are live (flag + overlay).
  // Drives two things only: the small mission label on a focus card, and
  // the zone card launching a mission-only session.
  const [lanesOn, setLanesOn] = useState(false);
  const [sessionZoneId, setSessionZoneId] = useState<number | null>(null);
  // Vacation mode (Phase 4.6): "" = home; otherwise the last paused day.
  const [vacationUntil, setVacationUntil] = useState("");
  const [runningCampaigns, setRunningCampaigns] = useState<Campaign[]>([]);
  const [celebratingId, setCelebratingId] = useState<number | null>(null);
  const [snoozingId, setSnoozingId] = useState<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // The Undo toast (Phase 9), keyed per completion so its linger timer
  // restarts; the ref holds the completion an undo would reverse.
  const [undoKey, setUndoKey] = useState<number | null>(null);
  const undoCompletionIdRef = useRef<number | null>(null);

  const loadFocus = useCallback((filter: EffortFilter) => {
    // Order behind any in-flight Done/Undo posts (e.g. an undo tapped
    // seconds ago in a session) so this fetch can't race a write and
    // show a list the server has already moved past.
    afterPendingWrites()
      .then(() => getFocus(filter === "all" ? undefined : filter))
      .then(setFocus)
      .catch(() => setFocus({ tasks: [], total_active_tasks: 0 }));
  }, []);

  useEffect(() => {
    loadFocus(effort);
  }, [effort, loadFocus]);

  // A PWA rarely restarts — refresh the list whenever the app returns
  // to the foreground so it never shows a stale morning.
  useEffect(() => {
    function onVisibility() {
      if (document.visibilityState === "visible") loadFocus(effort);
    }
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [effort, loadFocus]);

  useEffect(() => {
    // The overlays (SPEC §6, Phase 3) only ever appear when opted in —
    // toggled off, the home screen is exactly the core experience.
    getSettings()
      .then((s) => {
        setMinutes(s.default_session_minutes);
        setVacationUntil(s.vacation_until);
        setLanesOn(s.zones_enabled && s.zone_lane_enabled);
        if (s.zones_enabled) {
          getZones()
            .then((z) => {
              setCurrentZone(
                z.zones.find((zone) => zone.id === z.current_zone_id) ?? null,
              );
              // Only zones with rooms can scope a session — an empty
              // zone would just build an empty queue.
              setZones(z.zones.filter((zone) => zone.rooms.length > 0));
            })
            .catch(() => {});
        }
        if (s.campaigns_enabled) {
          getCampaigns()
            .then((all) => setRunningCampaigns(all.filter((c) => c.is_running)))
            .catch(() => {});
        }
      })
      .catch(() => {});
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  function startSession() {
    const params = new URLSearchParams({ minutes: String(minutes) });
    if (effort !== "all") params.set("effort", effort);
    if (sessionZoneId !== null) {
      params.set("zone", String(sessionZoneId));
      const zone = zones.find((z) => z.id === sessionZoneId);
      if (zone) params.set("label", zone.name);
    }
    router.push(`/session?${params.toString()}`);
  }

  async function endVacation() {
    const previous = vacationUntil;
    setVacationUntil(""); // optimistic — coming home should feel instant
    try {
      await updateSettings({ vacation_until: "" });
    } catch {
      setVacationUntil(previous); // roll back quietly, like Settings does
    }
  }

  function startChaosClean() {
    router.push(`/session?guest=1&minutes=${minutes}`);
  }

  function handleDone(task: Task) {
    if (celebratingId !== null) return;
    setCelebratingId(task.id);
    // The write fires NOW (issue #11): the celebration is presentation,
    // never a precondition — tapping a nav link mid-pop unmounts this
    // screen and cancels the timer, but the Done still lands. The
    // composed mission card logs source "zone" so zone history sees
    // completions made from home (issue #30).
    const post = trackWrite(
      completeTask(task.id, task.task_type === "zone" ? "zone" : "direct"),
    ).catch(() => null);
    timerRef.current = setTimeout(async () => {
      const done = await post;
      if (done) {
        // The burst has landed — now offer a quiet Undo for a beat
        // (Phase 9), in case that Done wasn't meant.
        undoCompletionIdRef.current = done.completion_id;
        setUndoKey((k) => (k ?? 0) + 1);
      }
      // On failure the reload below shows the honest state.
      setCelebratingId(null);
      loadFocus(effort);
    }, DONE_POP_MS);
  }

  function handleUndo() {
    const completionId = undoCompletionIdRef.current;
    undoCompletionIdRef.current = null;
    if (completionId === null) return;
    trackWrite(undoCompletion(completionId))
      .catch(() => {})
      .finally(() => loadFocus(effort));
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
  const onVacation = vacationUntil !== "" && toLocalDateValue() <= vacationUntil;

  return (
    <AppShell nav={NAV_ITEMS}>
      <header className={styles.greeting}>
        <h1 className={styles.hello}>Hi, {firstName} 👋</h1>
        <p className={styles.subline}>
          {needsSetup
            ? "Let’s get your home set up."
            : onVacation
              ? "You’re officially off duty."
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
      ) : onVacation ? (
        /* ---- Vacation mode (Phase 4.6): nudges paused, decay honest ---- */
        <Card padding="lg" className={styles.vacationCard}>
          <p className={styles.setupEmoji}>🌴</p>
          <h2 className={styles.setupTitle}>
            Everything’s paused until {friendlyDate(vacationUntil)}
          </h2>
          <p className={styles.setupBody}>
            No nudges while you’re away. Have a good trip 🌴
          </p>
          <Button variant="secondary" fullWidth onClick={endVacation}>
            I’m back!
          </Button>
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
            {/* Optional zone scope (Phase 4.6) — only when the zones
                overlay is on and at least one zone has rooms. */}
            {zones.length > 0 && (
              <select
                value={sessionZoneId ?? ""}
                onChange={(e) =>
                  setSessionZoneId(
                    e.target.value === "" ? null : Number(e.target.value),
                  )
                }
                className={styles.zoneSelect}
                aria-label="Focus on a zone (optional)"
              >
                <option value="">Anywhere in the house</option>
                {zones.map((zone) => (
                  <option key={zone.id} value={zone.id}>
                    🧭 Just {zone.name}
                  </option>
                ))}
              </select>
            )}
            <Button variant="primary" size="lg" fullWidth onClick={startSession}>
              I have {minutes} minutes
            </Button>
            {/* Guest / Chaos mode (SPEC §6): quick, high-visibility wins
                in guest-facing spots — for when company is on the way. */}
            <button
              type="button"
              className={styles.chaosLink}
              onClick={startChaosClean}
            >
              🚪 Company on the way? Chaos clean the guest spots
            </button>
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
                  {/* The composed mission card's one label (Phase 11) —
                      the home screen's entire visual budget. No counts,
                      no progress, no new elements. */}
                  {lanesOn && task.task_type === "zone" && (
                    <p className={styles.missionLabel}>
                      🧭 This week’s {task.zone_name ?? "zone"} mission
                    </p>
                  )}
                  <div className={styles.taskTop}>
                    <DirtinessDot band={task.band} />
                    <span className={styles.taskName}>{task.name}</span>
                    {task.room_name && (
                      <Chip tone={roomTone(task.room_id)}>{task.room_name}</Chip>
                    )}
                  </div>
                  <p className={styles.taskMeta}>about {task.estimated_minutes} min</p>
                  {/* Surfaced only because nothing else needs doing
                      (Issue #8) — still resting, so the card says so. */}
                  {task.is_snoozed && task.snoozed_until && (
                    <p className={styles.taskMeta}>
                      😴 {snoozedLabel(task.snoozed_until)}
                    </p>
                  )}
                  {supplyNote(task) && (
                    <p className={styles.supplyNote}>🧴 {supplyNote(task)}</p>
                  )}

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

          {/* ---- This week's zone (FlyLady overlay, opt-in) ---- */}
          {currentZone && (
            <Card className={styles.overlayCard}>
              <p className={styles.overlayLabel}>🧭 This week’s zone</p>
              <p className={styles.overlayTitle}>{currentZone.name}</p>
              {currentZone.rooms.length > 0 ? (
                <p className={styles.overlayMeta}>
                  {currentZone.rooms.map((r) => r.name).join(" · ")}
                </p>
              ) : (
                <p className={styles.overlayMeta}>
                  No rooms mapped yet — set that up in Settings.
                </p>
              )}
              <Button
                variant="secondary"
                fullWidth
                disabled={currentZone.rooms.length === 0}
                onClick={() =>
                  // missions=1 (Phase 11): a mission-only zone session.
                  // With the lanes off the backend ignores it and builds
                  // the legacy zone session — same button either way.
                  router.push(
                    `/session?zone=${currentZone.id}&minutes=${minutes}&missions=1&label=${encodeURIComponent(currentZone.name)}`,
                  )
                }
              >
                Give it {minutes} minutes
              </Button>
            </Card>
          )}

          {/* ---- Running seasonal campaigns (opt-in) ---- */}
          {runningCampaigns.map((campaign) => (
            <Card key={campaign.id} className={styles.overlayCard}>
              <p className={styles.overlayLabel}>
                🌷 {campaign.season ? `${campaign.season} campaign` : "Campaign"}
              </p>
              <p className={styles.overlayTitle}>{campaign.name}</p>
              <div
                className={styles.progressTrack}
                role="progressbar"
                aria-valuenow={campaign.percent}
                aria-valuemin={0}
                aria-valuemax={100}
              >
                <div
                  className={styles.progressFill}
                  style={{ width: `${campaign.percent}%` }}
                />
              </div>
              <p className={styles.overlayMeta}>
                {campaign.done_tasks} of {campaign.total_tasks} done —{" "}
                {campaign.percent === 100
                  ? "all wrapped up! 🎉"
                  : "no rush, it’s coming along."}
              </p>
              {campaign.percent < 100 && (
                <Button
                  variant="secondary"
                  fullWidth
                  onClick={() =>
                    router.push(
                      `/session?campaign=${campaign.id}&label=${encodeURIComponent(campaign.name)}`,
                    )
                  }
                >
                  Chip away at it
                </Button>
              )}
            </Card>
          ))}
        </>
      )}

      {/* ---- Done Today (Phase 5): the home screen's ONE new element —
           a quiet door to the rewards. Streaks and badges live behind
           it, never out here; the calm home screen is the product. ---- */}
      {focus !== null && !needsSetup && (
        <Link href="/done-today" className={styles.doneTodayLink}>
          ✨ See what you’ve gotten done today
        </Link>
      )}

      {/* Undo for the last Done (Phase 9) — an overlay, not a screen
          element, so the calm home stays exactly as it is. */}
      {undoKey !== null && (
        <UndoToast
          key={undoKey}
          onUndo={handleUndo}
          onGone={() => setUndoKey(null)}
        />
      )}
    </AppShell>
  );
}
