"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  ApiError,
  createMember,
  deleteMember,
  getMembers,
  updateMember,
  type Member,
} from "@/lib/api";
import { Button, Card, Chip } from "@/components/ui";
import styles from "./HouseholdSection.module.css";

type Role = "kid" | "owner";

function memberMeta(member: Member): string {
  const n = member.assigned_count;
  if (member.role === "owner") {
    return n === 0
      ? "adult"
      : `adult · ${n} ${n === 1 ? "task" : "tasks"} assigned`;
  }
  return n === 0
    ? "no chores assigned yet"
    : `${n} ${n === 1 ? "chore" : "chores"} assigned`;
}

/**
 * "Your crew" (SPEC §6 multi-user, Phase 2; adults since Phase 4.6):
 * everyone's PIN login lives here — kids AND extra adults. An adult
 * (role "owner") sees and can change everything, exactly like her; a
 * kid sees only their chores. Tapping a person opens the task list
 * filtered to what's assigned to them.
 */
export default function HouseholdSection({
  currentUserId,
}: {
  currentUserId: number;
}) {
  const [members, setMembers] = useState<Member[]>([]);
  const [newName, setNewName] = useState("");
  const [newPin, setNewPin] = useState("");
  const [newRole, setNewRole] = useState<Role>("kid");
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
      await createMember({ name: newName.trim(), pin: newPin, role: newRole });
      setNewName("");
      setNewPin("");
      setNewRole("kid");
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

  const addValid = newName.trim().length > 0 && /^\d{4,12}$/.test(newPin);

  return (
    <Card className={styles.section}>
      <h2 className={styles.heading}>Your crew</h2>
      <p className={styles.help}>
        Everyone logs in with their own PIN. An adult sees and can change
        everything, same as you; a kid sees just their chores — and you get
        a happy little ping each time they finish one. Tap a person to see
        what’s on their plate.
      </p>

      {members.map((member) =>
        editingId === member.id ? (
          <MemberEditor
            key={member.id}
            member={member}
            isSelf={member.id === currentUserId}
            onClose={(changed) => {
              setEditingId(null);
              if (changed) load();
            }}
          />
        ) : (
          <div key={member.id} className={styles.kidRow}>
            <Link
              href={`/tasks?assignee=${member.id}`}
              className={styles.kidBody}
            >
              <span className={styles.kidName}>
                {member.name}
                {member.id === currentUserId && (
                  <span className={styles.you}> (you)</span>
                )}
              </span>
              <span className={styles.kidMeta}>{memberMeta(member)}</span>
            </Link>
            <Button variant="ghost" onClick={() => setEditingId(member.id)}>
              Edit
            </Button>
          </div>
        ),
      )}

      <form onSubmit={handleAdd} className={styles.addForm}>
        <span className={styles.addLabel}>Add someone</span>
        <div className={styles.roleRow}>
          <Chip
            tone={newRole === "kid" ? "coral" : "neutral"}
            onClick={() => setNewRole("kid")}
          >
            A kid
          </Chip>
          <Chip
            tone={newRole === "owner" ? "coral" : "neutral"}
            onClick={() => setNewRole("owner")}
          >
            An adult
          </Chip>
        </div>
        <p className={styles.roleNote}>
          {newRole === "kid"
            ? "Kids see only their own chores and check them off."
            : "An adult sees and can change everything — tasks, lists, settings."}
        </p>
        <div className={styles.addRow}>
          <input
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="Name"
            className={styles.input}
            aria-label="Name"
          />
          <input
            type="password"
            inputMode="numeric"
            value={newPin}
            onChange={(e) => setNewPin(e.target.value.replace(/\D/g, ""))}
            placeholder="PIN"
            className={`${styles.input} ${styles.pinInput}`}
            aria-label="PIN"
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

function MemberEditor({
  member,
  isSelf,
  onClose,
}: {
  member: Member;
  isSelf: boolean;
  onClose: (changed: boolean) => void;
}) {
  const [name, setName] = useState(member.name);
  const [pin, setPin] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pinValid = pin === "" || /^\d{4,12}$/.test(pin);

  async function handleSave() {
    if (busy || !pinValid || name.trim().length === 0) return;
    setBusy(true);
    setError(null);
    try {
      await updateMember(member.id, {
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
    const stays =
      member.role === "kid"
        ? "Their assigned chores stay, just unassigned."
        : "Their assigned tasks stay, just unassigned.";
    if (!window.confirm(`Remove ${member.name}’s login? ${stays}`)) return;
    setBusy(true);
    try {
      await deleteMember(member.id);
      onClose(true);
    } catch (err) {
      // 409 = the last adult login; the backend explains it warmly.
      setError(
        err instanceof ApiError && err.status === 409
          ? err.message
          : "That didn’t work — give it another try.",
      );
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
        {/* Removing your own login from under yourself is never the
            right move — change the PIN or ask the other adult instead. */}
        {!isSelf && (
          <Button
            variant="ghost"
            onClick={handleRemove}
            disabled={busy}
            className={styles.removeButton}
          >
            Remove
          </Button>
        )}
      </div>
    </div>
  );
}
