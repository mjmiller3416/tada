"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  createMember,
  deleteMember,
  getMembers,
  updateMember,
  type Member,
} from "@/lib/api";
import { Button, Card } from "@/components/ui";
import styles from "./HouseholdSection.module.css";

/**
 * "Your crew" (SPEC §6 multi-user, Phase 2): add kid logins, rename them,
 * hand out fresh PINs, remove them. Kids see their chores and check them
 * off — that's the whole kid experience, so this is the whole admin.
 */
export default function HouseholdSection() {
  const [members, setMembers] = useState<Member[]>([]);
  const [newName, setNewName] = useState("");
  const [newPin, setNewPin] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);

  const load = useCallback(() => {
    getMembers()
      .then(setMembers)
      .catch(() => {});
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await createMember({ name: newName.trim(), pin: newPin });
      setNewName("");
      setNewPin("");
      load();
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 409
          ? err.message
          : "That didn’t work — check the name and PIN (4–12 digits).",
      );
    } finally {
      setBusy(false);
    }
  }

  const kids = members.filter((m) => m.role === "kid");
  const addValid = newName.trim().length > 0 && /^\d{4,12}$/.test(newPin);

  return (
    <Card className={styles.section}>
      <h2 className={styles.heading}>Your crew</h2>
      <p className={styles.help}>
        Kids get their own login — just a PIN. They see their chores and
        check them off, and you get a happy little ping each time.
      </p>

      {kids.map((kid) =>
        editingId === kid.id ? (
          <KidEditor
            key={kid.id}
            kid={kid}
            onClose={(changed) => {
              setEditingId(null);
              if (changed) load();
            }}
          />
        ) : (
          <div key={kid.id} className={styles.kidRow}>
            <span className={styles.kidBody}>
              <span className={styles.kidName}>{kid.name}</span>
              <span className={styles.kidMeta}>
                {kid.assigned_count === 0
                  ? "no chores assigned yet"
                  : `${kid.assigned_count} ${kid.assigned_count === 1 ? "chore" : "chores"} assigned`}
              </span>
            </span>
            <Button variant="ghost" onClick={() => setEditingId(kid.id)}>
              Edit
            </Button>
          </div>
        ),
      )}

      <form onSubmit={handleAdd} className={styles.addForm}>
        <span className={styles.addLabel}>Add a kid</span>
        <div className={styles.addRow}>
          <input
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="Name"
            className={styles.input}
            aria-label="Kid's name"
          />
          <input
            type="password"
            inputMode="numeric"
            value={newPin}
            onChange={(e) => setNewPin(e.target.value.replace(/\D/g, ""))}
            placeholder="PIN"
            className={`${styles.input} ${styles.pinInput}`}
            aria-label="Kid's PIN"
          />
          <Button type="submit" variant="secondary" disabled={busy || !addValid}>
            Add
          </Button>
        </div>
        {error && <p className={styles.error}>{error}</p>}
      </form>
    </Card>
  );
}

function KidEditor({
  kid,
  onClose,
}: {
  kid: Member;
  onClose: (changed: boolean) => void;
}) {
  const [name, setName] = useState(kid.name);
  const [pin, setPin] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pinValid = pin === "" || /^\d{4,12}$/.test(pin);

  async function handleSave() {
    if (busy || !pinValid || name.trim().length === 0) return;
    setBusy(true);
    setError(null);
    try {
      await updateMember(kid.id, {
        name: name.trim(),
        ...(pin !== "" ? { pin } : {}),
      });
      onClose(true);
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 409
          ? err.message
          : "That didn’t save — give it another try.",
      );
      setBusy(false);
    }
  }

  async function handleRemove() {
    if (busy) return;
    if (
      !window.confirm(
        `Remove ${kid.name}’s login? Their assigned chores stay, just unassigned.`,
      )
    )
      return;
    setBusy(true);
    try {
      await deleteMember(kid.id);
      onClose(true);
    } catch {
      setError("That didn’t work — give it another try.");
      setBusy(false);
    }
  }

  return (
    <div className={styles.editor}>
      <input
        type="text"
        value={name}
        onChange={(e) => setName(e.target.value)}
        className={styles.input}
        aria-label="Name"
      />
      <input
        type="password"
        inputMode="numeric"
        value={pin}
        onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
        placeholder="New PIN (blank keeps the old one)"
        className={styles.input}
        aria-label="New PIN"
      />
      {error && <p className={styles.error}>{error}</p>}
      <div className={styles.editorActions}>
        <Button
          variant="primary"
          onClick={handleSave}
          disabled={busy || !pinValid || name.trim().length === 0}
        >
          {busy ? "Saving…" : "Save"}
        </Button>
        <Button variant="ghost" onClick={() => onClose(false)} disabled={busy}>
          Cancel
        </Button>
        <Button
          variant="ghost"
          onClick={handleRemove}
          disabled={busy}
          className={styles.removeButton}
        >
          Remove
        </Button>
      </div>
    </div>
  );
}
