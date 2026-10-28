// The line's two pictures (review plan R4): the chain flow and the LOPA bar. Both draw only what
// the server stored: the chain's links in their stored order, each fact's stored value, each
// layer's stored PFD and reason, the stored mitigated and tolerable frequencies and gap. The one
// thing worked out here is where a frequency sits on a log axis.

import type { Evidence, LopaRecord } from "../api/schema";
import { keyName } from "./names";
import { calculationOf, isSkipped } from "./evidence";

// ---- chain flow -------------------------------------------------------------------------------

export type FlowCalculation = { id: string; verdict: string; summary: string };

export type FlowBox = {
  /** the link as stored: a finding ID or a plant fact ID (the drawer opens either) */
  id: string;
  kind: "finding" | "fact";
  name: string;
  /** the fact's stored value with its unit; null for a finding or a fact the plant lacks */
  value: string | null;
  /** a valve stored closed */
  closed: boolean;
  calculations: FlowCalculation[];
};

// the unit a field name's suffix carries (PROJECT.md §9), longest suffix first
const UNITS: [string, string][] = [
  ["_kj_kg_k", "kJ/kg·K"],
  ["_per_year", "/yr"],
  ["_kg_m3", "kg/m³"],
  ["_kj_kg", "kJ/kg"],
  ["_kpaa", "kPa(a)"],
  ["_kg_h", "kg/h"],
  ["_kpa", "kPa(g)"],
  ["_pct", "%"],
  ["_usd", "USD"],
  ["_m3", "m³"],
  ["_kw", "kW"],
  ["_mm", "mm"],
  ["_c", "°C"],
  ["_m", "m"],
];

function plain(value: unknown): string {
  if (Array.isArray(value)) return value.map(plain).join(", ");
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (value !== null && typeof value === "object") {
    // a value object: its medium or name, else its first text field
    const record = value as Record<string, unknown>;
    const named = record.medium ?? record.name;
    if (typeof named === "string") return named;
    const first = Object.values(record).find((v) => typeof v === "string");
    return typeof first === "string" ? first : JSON.stringify(value);
  }
  return String(value);
}

/** A fact's stored value as text, with the unit its field name carries. */
export function factText(factId: string, value: unknown): string {
  const field = factId.slice(factId.lastIndexOf(".") + 1);
  const unit = UNITS.find(([suffix]) => field.endsWith(suffix))?.[1];
  const text = plain(value);
  return unit !== undefined && typeof value === "number"
    ? `${text} ${unit}`
    : text;
}

const objectOf = (link: string) => link.split(".")[0] ?? link;

/** The chain's links as boxes, in the stored order; each calculation in the first box on its
 * equipment. */
export function chainFlow(
  links: readonly string[],
  factValues: Record<string, unknown>,
  evidence: readonly Evidence[],
): FlowBox[] {
  const boxes: FlowBox[] = links.map((link) => {
    const finding = link.startsWith("f:");
    const known = !finding && link in factValues;
    const value = known ? factValues[link] : undefined;
    return {
      id: link,
      kind: finding ? "finding" : "fact",
      name: keyName(link),
      value: known ? factText(link, value) : null,
      closed: link.endsWith(".normal_position") && value === "closed",
      calculations: [],
    };
  });
  for (const e of evidence) {
    const ref = calculationOf(e);
    if (ref === null || isSkipped(e)) continue;
    const holder = boxes.find(
      (b) => b.kind === "fact" && objectOf(b.id) === ref.equipment_id,
    );
    holder?.calculations.push({
      id: e.id,
      verdict: e.verdict,
      summary: e.summary,
    });
  }
  return boxes;
}

// ---- LOPA bar ---------------------------------------------------------------------------------

export type BarStep = {
  layer_id: string;
  layer_type: string | null;
  credited: boolean;
  pfd: number | null;
  reason: string;
  /** log10 of where the line sits after this layer */
  log_after: number;
};

export type LopaBar = {
  lopa_id: string;
  start: { label: string; per_year: number };
  steps: BarStep[];
  mitigated_per_year: number | null;
  tolerable_per_year: number;
  gap: number | null;
  log_max: number;
  log_min: number;
};

/** The LOPA as a staircase on a log axis; null when the record lacks its start or its limit. */
export function lopaBar(lopa: LopaRecord): LopaBar | null {
  const start = lopa.initiating_frequency_per_year;
  const tolerable = lopa.tolerable_per_year;
  if (start === null || start === undefined || start <= 0) return null;
  if (tolerable === null || tolerable === undefined || tolerable <= 0)
    return null;
  let at = Math.log10(start);
  const steps = (lopa.layers ?? []).map((layer) => {
    const pfd = layer.pfd ?? null;
    if (layer.credited && pfd !== null && pfd > 0) at += Math.log10(pfd);
    return {
      layer_id: layer.layer_id,
      layer_type: layer.layer_type ?? null,
      credited: layer.credited,
      pfd,
      reason: layer.reason,
      log_after: Number(at.toPrecision(12)),
    };
  });
  const mitigated = lopa.mitigated_frequency_per_year ?? null;
  const shown = [
    Math.log10(start),
    Math.log10(tolerable),
    ...steps.map((s) => s.log_after),
    ...(mitigated !== null && mitigated > 0 ? [Math.log10(mitigated)] : []),
  ];
  return {
    lopa_id: lopa.id,
    start: {
      label: lopa.initiating_event_id ?? "initiating event",
      per_year: start,
    },
    steps,
    mitigated_per_year: mitigated,
    tolerable_per_year: tolerable,
    gap: lopa.gap ?? null,
    log_max: Math.ceil(Math.max(...shown)),
    log_min: Math.floor(Math.min(...shown)) - 1,
  };
}
