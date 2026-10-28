// The coverage screen's view of the served counts (spec 5.4): a name per list, the totals at the
// top, and the failed questions with their text. The counts are the server's; this only adds
// them up for the top line.

import type { CoverageLine, Question } from "../api/schema";

// the `sections` line counts sections; every other line counts questions (backend coverage.py)
const SECTIONS = "sections";

const NAMES: Record<string, string> = {
  sections: "Sections",
  matrix: "Matrix",
  chemical_pair: "Chemical pairs",
  chemical_environment: "Chemical environment",
  no_flow_line: "No-flow lines",
  procedure_step: "Procedure steps",
  planned_work: "Planned work",
  dust: "Dust",
  relief_discharge: "Relief discharge",
  added_by_ai: "Added by AI",
  engineer: "Engineer",
};

export function listName(list: string): string {
  return NAMES[list] ?? list.replace(/_/g, " ");
}

export type Count = { checked: number; total: number };

/** "Checked X of Y" questions across the question lists, and the sections line on its own:
 * a section and a question are different things, so they are never added together. */
export function coverageTotals(lists: readonly CoverageLine[]): {
  questions: Count;
  sections: Count | null;
} {
  const questions = lists
    .filter((l) => l.list !== SECTIONS)
    .reduce(
      (sum, l) => ({
        checked: sum.checked + l.checked,
        total: sum.total + l.total,
      }),
      { checked: 0, total: 0 },
    );
  const sections = lists.find((l) => l.list === SECTIONS);
  return {
    questions,
    sections: sections
      ? { checked: sections.checked, total: sections.total }
      : null,
  };
}

export type FailedRow = { id: string; text: string | null };

/** Each failed question in the served order, with its text when its record loaded. */
export function failedRows(
  ids: readonly string[],
  questions: readonly Question[],
): FailedRow[] {
  const text = new Map(questions.map((q) => [q.id, q.text]));
  return ids.map((id) => ({ id, text: text.get(id) ?? null }));
}
