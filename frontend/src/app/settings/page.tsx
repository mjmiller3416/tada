"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import AuthGate from "@/components/AuthGate";
import HouseholdSection from "@/components/HouseholdSection";
import PushSubscribeButton from "@/components/PushSubscribeButton";
import {
  getRooms,
  getSettings,
  getZones,
  logout,
  setupZones,
  updateRoom,
  updateSettings,
  updateZone,
  type Room,
  type Settings,
  type ZonesResponse,
} from "@/lib/api";
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
  return <AuthGate ownerOnly>{() => <SettingsScreen />}</AuthGate>;
}

function SettingsScreen() {
  const router = useRouter();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [saved, setSaved] = useState(false);
  const [zonesData, setZonesData] = useState<ZonesResponse | null>(null);
  const [rooms, setRooms] = useState<Room[]>([]);
  const savedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadZoneEditor = useCallback(() => {
    getZones()
      .then(setZonesData)
      .catch(() => {});
    getRooms()
      .then(setRooms)
      .catch(() => {});
  }, []);

  useEffect(() => {
    getSettings()
      .then((s) => {
        setSettings(s);
        if (s.zones_enabled) loadZoneEditor();
      })
      .catch(() => {});
    return () => {
      if (savedTimer.current) clearTimeout(savedTimer.current);
    };
  }, [loadZoneEditor]);

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

  async function handleZonesToggle(on: boolean) {
    if (on) {
      // Seed FlyLady's five zones and auto-map rooms by name before
      // flipping the setting, so the editor below is never empty.
      // Re-running never moves a room she has already placed.
      await setupZones().then(setZonesData).catch(() => {});
      getRooms()
        .then(setRooms)
        .catch(() => {});
    }
    await save({ zones_enabled: on });
  }

  async function handleRoomZone(room: Room, value: string) {
    setRooms((current) =>
      current.map((r) =>
        r.id === room.id ? { ...r, zone_id: value === "" ? null : Number(value) } : r,
      ),
    );
    try {
      await updateRoom(
        room.id,
        value === "" ? { clear_zone: true } : { zone_id: Number(value) },
      );
    } finally {
      loadZoneEditor();
    }
  }

  async function handleZoneRename(zoneId: number, name: string) {
    if (!name.trim()) return;
    await updateZone(zoneId, { name: name.trim() })
      .then(setZonesData)
      .catch(() => {});
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

        <HouseholdSection />

        {/* ---- Phase 3 overlays: opt-in extras over the core (SPEC §6) ---- */}
        <Card className={styles.section}>
          <h2 className={styles.heading}>Extras</h2>
          <p className={styles.help}>
            Optional layers on top of your everyday rhythm — turn them on
            when they help, off when they don’t. Nothing else changes.
          </p>

          <label className={styles.toggleRow}>
            <input
              type="checkbox"
              checked={settings.zones_enabled}
              onChange={(e) => handleZonesToggle(e.target.checked)}
            />
            🧭 FlyLady zones — one area gets a little extra love each week
          </label>

          {settings.zones_enabled && zonesData && (
            <div className={styles.zoneEditor}>
              {zonesData.zones.map((zone) => (
                <div key={zone.id} className={styles.zoneRow}>
                  <span className={styles.zoneWeek}>
                    Week {zone.week_of_month}
                    {zone.id === zonesData.current_zone_id && " · now"}
                  </span>
                  <input
                    type="text"
                    defaultValue={zone.name}
                    onBlur={(e) => handleZoneRename(zone.id, e.target.value)}
                    className={styles.input}
                    aria-label={`Zone ${zone.week_of_month} name`}
                  />
                </div>
              ))}

              {rooms.length > 0 && (
                <div className={styles.setting}>
                  <span className={styles.label}>Which zone is each room in?</span>
                  {rooms.map((room) => (
                    <div key={room.id} className={styles.roomZoneRow}>
                      <span className={styles.roomZoneName}>{room.name}</span>
                      <select
                        value={room.zone_id ?? ""}
                        onChange={(e) => handleRoomZone(room, e.target.value)}
                        className={styles.input}
                        aria-label={`Zone for ${room.name}`}
                      >
                        <option value="">No zone</option>
                        {zonesData.zones.map((zone) => (
                          <option key={zone.id} value={zone.id}>
                            Week {zone.week_of_month} — {zone.name}
                          </option>
                        ))}
                      </select>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          <label className={styles.toggleRow}>
            <input
              type="checkbox"
              checked={settings.campaigns_enabled}
              onChange={(e) => save({ campaigns_enabled: e.target.checked })}
            />
            🌷 Seasonal campaigns — big projects, paced out gently
          </label>

          {settings.campaigns_enabled && (
            <Link href="/campaigns">
              <Button variant="secondary" fullWidth>
                Manage campaigns
              </Button>
            </Link>
          )}
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
