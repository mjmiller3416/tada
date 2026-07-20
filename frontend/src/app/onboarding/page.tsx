"use client";

import { useState } from "react";
import Link from "next/link";
import AuthGate from "@/components/AuthGate";
import { runOnboarding, type OnboardingRoomInput } from "@/lib/api";
import { Button, Card, Chip, Confetti } from "@/components/ui";
import styles from "./onboarding.module.css";

/**
 * The onboarding wizard (SPEC §6, Chromebook-first): pick rooms, add a
 * little household context, and auto-generate a starter schedule she can
 * edit — a working setup in a couple of minutes, never a blank page.
 */

const ROOM_TYPES: { type: string; label: string; icon: string }[] = [
  { type: "kitchen", label: "Kitchen", icon: "🍳" },
  { type: "bathroom", label: "Bathroom", icon: "🛁" },
  { type: "bedroom", label: "Bedroom", icon: "🛏️" },
  { type: "living_room", label: "Living room", icon: "🛋️" },
  { type: "dining_room", label: "Dining room", icon: "🍽️" },
  { type: "office", label: "Office", icon: "💻" },
  { type: "laundry", label: "Laundry", icon: "🧺" },
  { type: "entryway", label: "Entryway", icon: "🚪" },
  { type: "hallway", label: "Hallway", icon: "🪜" },
  { type: "playroom", label: "Playroom", icon: "🧸" },
  { type: "garage", label: "Garage", icon: "🚗" },
  { type: "basement", label: "Basement", icon: "🔦" },
  { type: "custom", label: "Something else", icon: "✨" },
];

type Step = "welcome" | "rooms" | "household" | "done";

type PickedRoom = OnboardingRoomInput & { key: number };

export default function OnboardingPage() {
  return (
    <AuthGate ownerOnly>{(user) => <Wizard firstName={user.name.split(" ")[0]} />}</AuthGate>
  );
}

function Wizard({ firstName }: { firstName: string }) {
  const [step, setStep] = useState<Step>("welcome");
  const [picked, setPicked] = useState<PickedRoom[]>([]);
  const [nextKey, setNextKey] = useState(1);
  const [hasPets, setHasPets] = useState(false);
  const [hasKids, setHasKids] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ rooms: number; tasks: number } | null>(null);
  const [confetti, setConfetti] = useState(false);

  function addRoom(type: string, label: string) {
    const base = type === "custom" ? "Another room" : label;
    const existing = picked.filter((r) => r.name.startsWith(base)).length;
    const name = existing === 0 ? base : `${base} ${existing + 1}`;
    setPicked([...picked, { key: nextKey, type, name }]);
    setNextKey(nextKey + 1);
  }

  function renameRoom(key: number, name: string) {
    setPicked(picked.map((r) => (r.key === key ? { ...r, name } : r)));
  }

  function removeRoom(key: number) {
    setPicked(picked.filter((r) => r.key !== key));
  }

  async function generate() {
    if (generating) return;
    setGenerating(true);
    setError(null);
    try {
      const res = await runOnboarding({
        rooms: picked.map(({ name, type }) => ({ name: name.trim() || "Room", type })),
        has_pets: hasPets,
        has_kids: hasKids,
      });
      setResult({ rooms: res.rooms_created, tasks: res.tasks_created });
      setStep("done");
      setConfetti(true);
    } catch {
      setError("Something hiccuped — give it another try.");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <main className={styles.page}>
      <Confetti active={confetti} onComplete={() => setConfetti(false)} />

      <div className={styles.column}>
        {step === "welcome" && (
          <Card padding="lg" className={styles.stepCard}>
            <p className={styles.bigEmoji}>🏡</p>
            <h1 className={styles.title}>Hi, {firstName}!</h1>
            <p className={styles.body}>
              Let’s set up your home. Pick your rooms, tell us a little about
              your household, and Tada will build a working cleaning schedule
              for you — you can tweak anything afterwards.
            </p>
            <p className={styles.hint}>
              Takes about two minutes. Comfiest on the Chromebook, but the
              phone works too.
            </p>
            <Button variant="primary" size="lg" fullWidth onClick={() => setStep("rooms")}>
              Let’s go
            </Button>
          </Card>
        )}

        {step === "rooms" && (
          <Card padding="lg" className={styles.stepCard}>
            <h1 className={styles.title}>Which rooms do you have?</h1>
            <p className={styles.body}>
              Tap to add — tap again for a second bathroom or bedroom.
            </p>

            <div className={styles.typeGrid}>
              {ROOM_TYPES.map((rt) => (
                <button
                  key={rt.type}
                  type="button"
                  className={styles.typeButton}
                  onClick={() => addRoom(rt.type, rt.label)}
                >
                  <span className={styles.typeIcon}>{rt.icon}</span>
                  {rt.label}
                </button>
              ))}
            </div>

            {picked.length > 0 && (
              <div className={styles.pickedList}>
                {picked.map((room) => (
                  <div key={room.key} className={styles.pickedRow}>
                    <input
                      type="text"
                      value={room.name}
                      onChange={(e) => renameRoom(room.key, e.target.value)}
                      className={styles.input}
                      aria-label="Room name"
                    />
                    <Button variant="ghost" onClick={() => removeRoom(room.key)}>
                      ✕
                    </Button>
                  </div>
                ))}
              </div>
            )}

            <Button
              variant="primary"
              size="lg"
              fullWidth
              disabled={picked.length === 0}
              onClick={() => setStep("household")}
            >
              {picked.length === 0
                ? "Add a room to continue"
                : `Continue with ${picked.length} ${picked.length === 1 ? "room" : "rooms"}`}
            </Button>
            <Link href="/" className={styles.quietLink}>
              I’ll do this later
            </Link>
          </Card>
        )}

        {step === "household" && (
          <Card padding="lg" className={styles.stepCard}>
            <h1 className={styles.title}>A little about your household</h1>
            <p className={styles.body}>
              This just tunes how often things come up — floors with pets,
              tidying with kids.
            </p>

            <div className={styles.toggleList}>
              <Chip
                tone={hasPets ? "coral" : "neutral"}
                onClick={() => setHasPets(!hasPets)}
              >
                🐾 We have pets {hasPets ? "✓" : ""}
              </Chip>
              <Chip
                tone={hasKids ? "coral" : "neutral"}
                onClick={() => setHasKids(!hasKids)}
              >
                🧒 Kids live here {hasKids ? "✓" : ""}
              </Chip>
            </div>

            {error && <p className={styles.error}>{error}</p>}

            <Button
              variant="primary"
              size="lg"
              fullWidth
              onClick={generate}
              disabled={generating}
            >
              {generating ? "Building your schedule…" : "Build my schedule"}
            </Button>
            <Button variant="ghost" fullWidth onClick={() => setStep("rooms")}>
              Back to rooms
            </Button>
          </Card>
        )}

        {step === "done" && result && (
          <Card padding="lg" className={styles.stepCard}>
            <p className={styles.bigEmoji}>🎉</p>
            <h1 className={styles.title}>Ta-da! You’re set up.</h1>
            <p className={styles.body}>
              We made {result.tasks} starter tasks across {result.rooms}{" "}
              {result.rooms === 1 ? "room" : "rooms"}, each with a sensible
              rhythm. Everything is editable — tweak away, or just start.
            </p>
            <Link href="/tasks">
              <Button variant="primary" size="lg" fullWidth>
                Review my tasks
              </Button>
            </Link>
            <Link href="/">
              <Button variant="ghost" fullWidth>
                Take me home
              </Button>
            </Link>
          </Card>
        )}
      </div>
    </main>
  );
}
