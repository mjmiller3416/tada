"use client";

import { useState } from "react";
import {
  AppShell,
  Button,
  Card,
  Chip,
  Confetti,
  FocusCard,
  ProgressDots,
  type ChipTone,
} from "@/components/ui";
import styles from "./preview.module.css";

/**
 * Phase 0.5 kitchen sink — renders every UI primitive in its states so
 * the look and feel can be eyeballed before any feature UI is built.
 * Not linked from the app; visit /preview directly.
 */

const NAV_ITEMS = [
  { href: "/preview", label: "Today", icon: "🏠" },
  { href: "/preview/rooms", label: "Rooms", icon: "🛋️" },
  { href: "/preview/tasks", label: "Tasks", icon: "🧺" },
  { href: "/preview/settings", label: "Settings", icon: "⚙️" },
];

const SWATCHES: { name: string; varName: string }[] = [
  { name: "Purple (go / celebrate)", varName: "--color-purple" },
  { name: "Purple strong", varName: "--color-purple-strong" },
  { name: "Purple soft", varName: "--color-purple-soft" },
  { name: "Teal (done)", varName: "--color-teal" },
  { name: "Teal strong", varName: "--color-teal-strong" },
  { name: "Teal soft", varName: "--color-teal-soft" },
  { name: "Coral (rare accent)", varName: "--color-coral" },
  { name: "Coral strong", varName: "--color-coral-strong" },
  { name: "Coral soft", varName: "--color-coral-soft" },
  { name: "Background", varName: "--color-bg" },
  { name: "Surface", varName: "--color-surface" },
  { name: "Ink", varName: "--color-ink" },
  { name: "Ink soft", varName: "--color-ink-soft" },
  { name: "Line", varName: "--color-line" },
  { name: "Fresh", varName: "--status-fresh" },
  { name: "Aging", varName: "--status-aging" },
  { name: "Due", varName: "--status-due" },
  { name: "Overdue", varName: "--status-overdue" },
];

const CHIP_TONES: ChipTone[] = [
  "peach",
  "berry",
  "lavender",
  "periwinkle",
  "mint",
  "coral",
  "teal",
  "neutral",
];

const DEMO_TASKS = [
  { room: "Kitchen", tone: "mint" as ChipTone, name: "Wipe down the counters", minutes: 5 },
  { room: "Living room", tone: "lavender" as ChipTone, name: "Reset the couch pillows", minutes: 5 },
  { room: "Bathroom", tone: "periwinkle" as ChipTone, name: "Shine the sink", minutes: 10 },
];

export default function PreviewPage() {
  const [taskIndex, setTaskIndex] = useState(0);
  const [confetti, setConfetti] = useState(false);

  const sessionDone = taskIndex >= DEMO_TASKS.length;

  function advance() {
    const next = taskIndex + 1;
    setTaskIndex(next);
    if (next >= DEMO_TASKS.length) setConfetti(true);
  }

  function resetSession() {
    setTaskIndex(0);
    setConfetti(false);
  }

  return (
    <AppShell title="Tada — design preview" nav={NAV_ITEMS}>
      <Confetti active={confetti} onComplete={() => setConfetti(false)} />

      <p className={styles.intro}>
        Every Phase 0.5 primitive in its states, built only from the design
        tokens in <code>globals.css</code>.
      </p>

      {/* ---- Palette ---- */}
      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Palette</h2>
        <div className={styles.swatchGrid}>
          {SWATCHES.map((s) => (
            <div key={s.varName} className={styles.swatch}>
              <span
                className={styles.swatchColor}
                style={{ background: `var(${s.varName})` }}
              />
              <span className={styles.swatchName}>{s.name}</span>
            </div>
          ))}
        </div>
      </section>

      {/* ---- Typography ---- */}
      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Typography</h2>
        <Card>
          <p className={styles.typeXl}>Nice work — the kitchen sparkles.</p>
          <p className={styles.typeBase}>
            Regular weight (500) for body copy. Warm, first-name, always
            encouraging — never guilt.
          </p>
          <p className={styles.typeBold}>Bold weight (800) for emphasis.</p>
          <p className={styles.typeSoft}>
            Soft ink for quiet secondary details, like time estimates.
          </p>
        </Card>
      </section>

      {/* ---- Buttons ---- */}
      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Buttons</h2>
        <div className={styles.row}>
          <Button variant="primary">I have 15 minutes</Button>
          <Button variant="success">Done!</Button>
          <Button variant="secondary">Edit tasks</Button>
          <Button variant="ghost">Skip for now</Button>
        </div>
        <div className={styles.row}>
          <Button variant="primary" size="lg">
            Start a session
          </Button>
          <Button variant="primary" disabled>
            Disabled
          </Button>
        </div>
        <Button variant="primary" size="lg" fullWidth>
          Full width — the big go button
        </Button>
      </section>

      {/* ---- Chips ---- */}
      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Chips</h2>
        <div className={styles.row}>
          {CHIP_TONES.map((tone) => (
            <Chip key={tone} tone={tone}>
              {tone[0].toUpperCase() + tone.slice(1)}
            </Chip>
          ))}
        </div>
        <div className={styles.row}>
          <Chip tone="mint" onClick={() => {}}>
            Kitchen (tappable)
          </Chip>
          <Chip tone="peach" onClick={() => {}}>
            15 min
          </Chip>
        </div>
      </section>

      {/* ---- Card ---- */}
      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Card</h2>
        <Card>
          <p className={styles.cardText}>
            A soft, rounded surface with a warm shadow. Cards hold every
            content block in the app.
          </p>
        </Card>
      </section>

      {/* ---- Progress dots ---- */}
      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Progress signal</h2>
        <Card>
          <div className={styles.dotsRow}>
            <ProgressDots total={3} current={1} />
            <span className={styles.dotsLabel}>1 of 3</span>
          </div>
          <div className={styles.dotsRow}>
            <ProgressDots total={3} current={2} />
            <span className={styles.dotsLabel}>2 of 3</span>
          </div>
          <div className={styles.dotsRow}>
            <ProgressDots total={5} current={4} />
            <span className={styles.dotsLabel}>4 of 5</span>
          </div>
        </Card>
      </section>

      {/* ---- Focus card (interactive) ---- */}
      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Focus card</h2>
        <p className={styles.hint}>
          Live demo: Done plays the pop and advances; Skip advances quietly.
          Finishing all three fires the confetti.
        </p>

        {!sessionDone ? (
          <FocusCard
            key={taskIndex}
            roomName={DEMO_TASKS[taskIndex].room}
            roomTone={DEMO_TASKS[taskIndex].tone}
            taskName={DEMO_TASKS[taskIndex].name}
            estimatedMinutes={DEMO_TASKS[taskIndex].minutes}
            current={taskIndex + 1}
            total={DEMO_TASKS.length}
            onDone={advance}
            onSkip={advance}
          />
        ) : (
          <Card padding="lg" className={styles.sessionDone}>
            <p className={styles.sessionDoneEmoji}>🎉</p>
            <h3 className={styles.sessionDoneTitle}>Ta-da! Session complete.</h3>
            <p className={styles.sessionDoneBody}>
              Three tasks down — your home says thank you.
            </p>
            <Button variant="primary" onClick={resetSession}>
              Run the demo again
            </Button>
          </Card>
        )}
      </section>

      {/* ---- Celebration ---- */}
      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Celebration</h2>
        <Button variant="success" onClick={() => setConfetti(true)}>
          Fire the confetti
        </Button>
      </section>

      {/* ---- Bottom nav note ---- */}
      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>App shell</h2>
        <p className={styles.hint}>
          This page renders inside the AppShell primitive — the title bar
          above and the bottom nav below are the shell itself.
        </p>
      </section>
    </AppShell>
  );
}
