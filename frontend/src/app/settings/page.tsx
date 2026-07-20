"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import AuthGate from "@/components/AuthGate";
import PushSubscribeButton from "@/components/PushSubscribeButton";
import { getSettings, logout, updateSettings, type Settings } from "@/lib/api";
import { NAV_ITEMS } from "@/lib/nav";
import { AppShell, Button, Card, Chip } from "@/components/ui";
import styles from "./settings.module.css";

const FOCUS_CHOICES = [1, 2, 3];
const MINUTE_CHOICES = [5, 15, 30, 45];

const TIMEZONES: { value: string; label: string }[] = [
  { value: "America/New_York", label: "Eastern" },
  { value: "America/Chicago", label: "Central" },
  { value: "America/Denver", label: "Mountain" },
  { value: "America/Phoenix", label: "Arizona" },
  { value: "America/Los_Angeles", label: "Pacific" },
  { value: "America/Anchorage", label: "Alaska" },
  { value: "Pacific/Honolulu", label: "Hawaii" },
];

/**
 * Settings (SPEC §6): the daily focus count, the default session budget,
 * the morning nudge, and this device's notifications. Changes save as
 * you tap — no form to submit.
 */
export default function SettingsPage() {
  return <AuthGate>{() => <SettingsScreen />}</AuthGate>;
}

function SettingsScreen() {
  const router = useRouter();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [saved, setSaved] = useState(false);
  const savedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    getSettings()
      .then(setSettings)
      .catch(() => {});
    return () => {
      if (savedTimer.current) clearTimeout(savedTimer.current);
    };
  }, []);

  async function save(patch: Partial<Settings>) {
    if (!settings) return;
    const next = { ...settings, ...patch };
    setSettings(next); // optimistic — settings taps should feel instant
    try {
      await updateSettings(patch);
      setSaved(true);
      if (savedTimer.current) clearTimeout(savedTimer.current);
      savedTimer.current = setTimeout(() => setSaved(false), 1500);
    } catch {
      setSettings(settings); // roll back quietly
    }
  }

  async function handleLogout() {
    await logout().catch(() => {});
    router.replace("/login");
  }

  if (!settings) {
    return <AppShell title="Settings" nav={NAV_ITEMS}>{null}</AppShell>;
  }

  const nudgeOn = settings.daily_nudge_time !== "";

  return (
    <AppShell title="Settings" nav={NAV_ITEMS}>
      <div className={styles.savedNote} aria-live="polite">
        {saved ? "Saved ✓" : " "}
      </div>

      <div className={styles.sections}>
        <Card className={styles.section}>
          <h2 className={styles.heading}>Your day</h2>

          <div className={styles.setting}>
            <span className={styles.label}>Tasks on your home screen</span>
            <div className={styles.chips}>
              {FOCUS_CHOICES.map((n) => (
                <Chip
                  key={n}
                  tone={settings.daily_focus_count === n ? "coral" : "neutral"}
                  onClick={() => save({ daily_focus_count: n })}
                >
                  {n}
                </Chip>
              ))}
            </div>
          </div>

          <div className={styles.setting}>
            <span className={styles.label}>Usual session length</span>
            <div className={styles.chips}>
              {MINUTE_CHOICES.map((m) => (
                <Chip
                  key={m}
                  tone={settings.default_session_minutes === m ? "coral" : "neutral"}
                  onClick={() => save({ default_session_minutes: m })}
                >
                  {m} min
                </Chip>
              ))}
            </div>
          </div>
        </Card>

        <Card className={styles.section}>
          <h2 className={styles.heading}>Morning nudge</h2>
          <p className={styles.help}>
            One gentle push a day with a good place to start — never more.
          </p>

          <label className={styles.toggleRow}>
            <input
              type="checkbox"
              checked={nudgeOn}
              onChange={(e) =>
                save({ daily_nudge_time: e.target.checked ? "08:30" : "" })
              }
            />
            Send me a morning nudge
          </label>

          {nudgeOn && (
            <div className={styles.setting}>
              <span className={styles.label}>Around what time?</span>
              <input
                type="time"
                value={settings.daily_nudge_time}
                onChange={(e) =>
                  e.target.value && save({ daily_nudge_time: e.target.value })
                }
                className={styles.input}
              />
            </div>
          )}

          <div className={styles.setting}>
            <span className={styles.label}>Your timezone</span>
            <select
              value={settings.timezone}
              onChange={(e) => save({ timezone: e.target.value })}
              className={styles.input}
            >
              {TIMEZONES.map((tz) => (
                <option key={tz.value} value={tz.value}>
                  {tz.label}
                </option>
              ))}
              {!TIMEZONES.some((tz) => tz.value === settings.timezone) && (
                <option value={settings.timezone}>{settings.timezone}</option>
              )}
            </select>
          </div>
        </Card>

        <Card className={styles.section}>
          <h2 className={styles.heading}>Notifications on this device</h2>
          <p className={styles.help}>
            Turn this on for each device you want nudges on (phone and
            Chromebook each count once).
          </p>
          <PushSubscribeButton />
        </Card>

        <Button variant="ghost" fullWidth onClick={handleLogout}>
          Log out
        </Button>
      </div>
    </AppShell>
  );
}
