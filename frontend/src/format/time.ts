// Dates and times as the screens show them, in UTC like the stored records.

/** "2026-10-22" from an ISO time. */
export function day(iso: string | null | undefined): string {
  return iso ? iso.slice(0, 10) : "—";
}

/** "14:05:00" from an ISO time. */
export function clock(iso: string | null | undefined): string {
  return iso ? new Date(iso).toISOString().slice(11, 19) : "—";
}
