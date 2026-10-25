// A line's evidence as the engineer reads it (Bhargavi's review, 2026-10-25): which calculation a
// card is and on which equipment, read from its ID (PROJECT.md §11:
// `ev:<line>:calculation:<calculation name>-<equipment id>`), and a skipped calculation as one
// line. Nothing here computes or attaches evidence; the server does.

import type { Evidence } from "../api/schema";

// the names the backend's physics tool gives each calculation (tools/physics.py `_skipped`)
export const CALCULATION_NAMES: Record<string, string> = {
  blocked_in_heating: "Blocked-in heating check",
  overflow_time: "Overflow time",
  heat_up_rate: "Heat-up time",
};

const MARK = ":calculation:";
// the shortlist's flag for a line whose evidence was skipped (review/shortlist.py)
const SKIP_FLAG = "evidence skipped: missing ";

export type CalculationRef = { calculation: string; equipment_id: string };

/** The calculation and equipment a calculation card is on; null for any other card. */
export function calculationOf(e: Evidence): CalculationRef | null {
  if (e.kind !== "calculation") return null;
  const at = e.id.lastIndexOf(MARK);
  if (at < 0) return null;
  const rest = e.id.slice(at + MARK.length);
  // calculation names have no hyphen; equipment IDs may
  const dash = rest.indexOf("-");
  if (dash < 0) return null;
  return {
    calculation: rest.slice(0, dash),
    equipment_id: rest.slice(dash + 1),
  };
}

/** A calculation that could not run: it names the plant facts it lacked. */
export function isSkipped(e: Evidence): boolean {
  return e.kind === "calculation" && (e.missing_fact_ids ?? []).length > 0;
}

function factCount(n: number): string {
  return n === 1 ? "1 plant fact missing" : `${n} plant facts missing`;
}

/** "Heat-up time skipped: 11 plant facts missing". */
export function skippedLine(e: Evidence): string {
  const ref = calculationOf(e);
  const name =
    ref === null
      ? "Calculation"
      : (CALCULATION_NAMES[ref.calculation] ?? ref.calculation);
  return `${name} skipped: ${factCount((e.missing_fact_ids ?? []).length)}`;
}

/** A flag as shown: the skip flag gives a count (its card lists the facts); others verbatim. */
export function shownFlag(flag: string): string {
  if (!flag.startsWith(SKIP_FLAG)) return flag;
  const facts = flag
    .slice(SKIP_FLAG.length)
    .split(", ")
    .filter((f) => f !== "");
  return `evidence skipped: ${factCount(facts.length)}`;
}
