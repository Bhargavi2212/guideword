// The technical layer under a line's plain title (review plan R3): the tags the line names, the
// LOPA line, the severity code with the reference table's own definition, and the gap as
// "N× over the risk limit" (Q10). Every number comes from the served record as stored and goes
// through the one number formatter; nothing here computes a risk.

import type { LopaRecord, Shortlist, ShortlistItem } from "../api/schema";
import { frequency } from "../format/number";
import { findingQuestion } from "./titles";

type SeverityClass = Shortlist["severity_classes"][number];

function unique(values: string[]): string[] {
  return values.filter((v, n) => v !== "" && values.indexOf(v) === n);
}

/** The objects a question ID names: a section's object, a step, a line, a chemical pair. */
function questionObjects(question: string): string[] {
  const [kind = "", a = "", b = ""] = question.split(":");
  if (kind === "m" || kind === "ai" || kind === "eng") {
    return a.replace(/^S-/, "").split("~");
  }
  if (kind === "pair" || kind === "work") return [a, b];
  return [a];
}

/** The equipment, valves, steps and chemicals the line names, each once, in order. */
export function lineTags(item: ShortlistItem): string[] {
  if (item.target_kind === "hypothesis")
    return item.hypothesis?.component_ids ?? [];
  if (item.target_kind === "chain") {
    const links = item.chain?.links ?? [];
    return unique(
      links.flatMap((link) =>
        link.startsWith("f:")
          ? questionObjects(findingQuestion(link))
          : [link.split(".")[0] ?? link],
      ),
    );
  }
  return item.finding?.failing_component_ids ?? [];
}

/** "1,000× over the risk limit"; "within the risk limit" at 1 or under (Q10). */
export function gapWords(item: ShortlistItem): string {
  if (!item.lopa) return "no LOPA";
  const gap = item.gap ?? item.lopa.gap ?? null;
  if (gap === null || gap === undefined)
    return "gap unknown: the LOPA is incomplete";
  if (gap <= 1) return "within the risk limit";
  const times = Number(gap.toPrecision(2)).toLocaleString("en-US");
  return `${times}× over the risk limit`;
}

/** "initiating event IE-X at 0.1 /yr · 1 of 2 layers credited · mitigated … against tolerable …". */
export function lopaLine(lopa: LopaRecord): string {
  const layers = lopa.layers ?? [];
  const credited = layers.filter((l) => l.credited).length;
  return [
    `initiating event ${lopa.initiating_event_id ?? "not named"} at ${frequency(lopa.initiating_frequency_per_year)}`,
    `${String(credited)} of ${String(layers.length)} layers credited`,
    `mitigated ${frequency(lopa.mitigated_frequency_per_year)} against tolerable ${frequency(lopa.tolerable_per_year)}`,
  ].join(" · ");
}

/** "S3 Serious: <the table's definition>"; the code alone when the table lacks it. */
export function severityText(
  code: string,
  classes: readonly SeverityClass[],
): string {
  const row = classes.find((c) => c.severity_class === code);
  return row ? `${code} ${row.name}: ${row.definition}` : code;
}
