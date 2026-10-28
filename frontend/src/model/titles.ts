// A shortlist line's plain title (review plan R3): one fixed template per line kind, written in
// code and filled from the line's own IDs only, never from model text. The card shows it on top;
// the technical layer sits below it.

import type { ShortlistItem } from "../api/schema";

// every template the card can show; `{…}` are filled from the question ID's parts
export const TEMPLATES: Record<string, string> = {
  m: "{Guideword} {parameter} at {object}",
  proc: "Step {step} {done}",
  pair: "{chemical} and {chemical} mix",
  env: "{chemical} meets {water | air | heat}",
  nf: "No flow in line {line}",
  work: "Planned work {job} on {object}",
  dust: "Dust at {object}",
  relief: "Where {device} discharges",
  ai: "Question added by the analysis on {object}",
  eng: "Engineer's question on {object}",
  chain: "{n} failures together: {title} and {title}",
  hypothesis: "Whole-plant hypothesis #{rank}",
};

const GUIDEWORDS: Record<string, string> = {
  no: "No",
  more: "More",
  less: "Less",
  reverse: "Reverse",
  other_than: "Other than",
  as_well_as: "As well as",
  part_of: "Part of",
  early: "Early",
  late: "Late",
  before: "Before",
  after: "After",
};

// what went wrong with a procedure step, by its guideword
const DONE: Record<string, string> = {
  early: "done too early",
  late: "done too late",
  skipped: "skipped",
  wrong: "done wrongly",
  out_of_order: "done out of order",
  more: "done too much",
  less: "done too little",
  no: "not done",
  before: "done before its time",
  after: "done after its time",
  reverse: "done in reverse",
};

// how many parts each question kind's ID has after its prefix (backend `schema/ids.py`)
const PARTS: Record<string, number> = {
  m: 3,
  pair: 2,
  env: 2,
  nf: 1,
  proc: 2,
  work: 2,
  dust: 1,
  relief: 1,
  ai: 2,
  eng: 2,
};

function words(value: string): string {
  return value.replace(/_/g, " ");
}

/** A section ID's object: `S-EA-425B` -> `EA-425B`; a split `S-L-1~E-1` -> `L-1 (E-1)`. */
function sectionObject(section: string): string {
  const bare = section.startsWith("S-") ? section.slice(2) : section;
  const [line, component] = bare.split("~");
  return component ? `${line ?? ""} (${component})` : (line ?? bare);
}

/** The question a finding ID was found on: its prefix and that kind's parts. */
export function findingQuestion(findingId: string): string {
  const parts = findingId.replace(/^f:/, "").split(":");
  const kind = parts[0] ?? "";
  return parts.slice(0, 1 + (PARTS[kind] ?? parts.length - 1)).join(":");
}

export function questionTitle(question: string): string {
  const [kind = "", a = "", b = "", c = ""] = question.split(":");
  switch (kind) {
    case "m":
      return `${GUIDEWORDS[b] ?? words(b)} ${words(c)} at ${sectionObject(a)}`;
    case "proc":
      return `Step ${a} ${DONE[b] ?? `done ${words(b)}`}`;
    case "pair":
      return `${a} and ${b} mix`;
    case "env":
      return `${a} meets ${words(b)}`;
    case "nf":
      return `No flow in line ${a}`;
    case "work":
      return `Planned work ${a} on ${b}`;
    case "dust":
      return `Dust at ${a}`;
    case "relief":
      return `Where ${a} discharges`;
    case "ai":
      return `Question added by the analysis on ${sectionObject(a)}`;
    case "eng":
      return `Engineer's question on ${sectionObject(a)}`;
    default:
      return [a, b, c].filter(Boolean).map(words).join(" ") || "A finding";
  }
}

export function lineTitle(item: ShortlistItem): string {
  if (item.target_kind === "hypothesis") {
    return `Whole-plant hypothesis #${String(item.hypothesis?.rank ?? item.rank)}`;
  }
  if (item.target_kind === "chain") {
    const findings = (item.chain?.links ?? []).filter((l) =>
      l.startsWith("f:"),
    );
    // two findings on one question read as one title, said once (D #6)
    const titles = findings
      .map((f) => questionTitle(findingQuestion(f)))
      .filter((t, n, all) => all.indexOf(t) === n);
    return `${String(findings.length)} failures together: ${titles.join(" and ")}`;
  }
  return questionTitle(
    item.finding?.question_id ?? findingQuestion(item.target_id),
  );
}
