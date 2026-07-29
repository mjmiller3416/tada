/** Local-calendar date helpers (Phase 4.6). Last-done corrections and
 * vacation mode both live in her local day — never UTC — so every
 * conversion to and from `<input type="date">` values goes through here. */

/** A Date (or ISO timestamp) as the local YYYY-MM-DD a date input wants.
 * With no argument: today. */
export function toLocalDateValue(date: Date | string = new Date()): string {
  const d = typeof date === "string" ? new Date(date) : date;
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${month}-${day}`;
}

/** A date-input value as local midnight, in the ISO form the API takes. */
export function fromLocalDateValue(value: string): string {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day).toISOString();
}

/** "2026-08-03" → "Aug 3" — for warm copy, not data. */
export function friendlyDate(value: string): string {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}
