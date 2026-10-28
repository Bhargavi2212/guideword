// The live-run timeline (spec 5.3, P5-1, P5-4): pure functions over a run's events as served.
// Nothing here reorders, drops or adds an event: every event lands in exactly one place, in
// `seq` order. The tier on a model call or dispatch is the server's (C3), never worked out here.

import type { CoverageLine, EventsPage, Run } from "../api/schema";
import type { components } from "../api/types";
import { money } from "../format/number";

type S = components["schemas"];

export type ApiEvent = EventsPage["events"][number];

// The payload each event type carries, v1.9 or legacy (the backend validated it; P5-1). A
// legacy payload may lack a v1.9 field, so each reader below treats it as optional.
type StepFinished = { step: string; status: string; next_step: string };
type Payloads = {
  run_started: S["RunStarted"] | S["LegacyRunStarted"];
  step_started: S["StepStarted"] | S["LegacyStepStarted"];
  step_finished: StepFinished;
  agent_decision: S["AgentDecision"] | S["LegacyAgentDecision"];
  dispatch: {
    agent: string;
    level: string;
    question_ids: string[];
    selected_by_code: boolean;
    priority?: boolean;
    batches?: number;
    tier?: S["Tier"] | null;
    tier_source?: "recorded" | "inferred" | null;
  };
  model_call: {
    job: string;
    model_id: string;
    cache_hit: boolean;
    outcome: string;
    cost_usd: number;
    cap_cost_usd: number;
    tier?: S["Tier"] | null;
    tier_source?: "recorded" | "inferred" | null;
  };
  tool_call: S["ToolCallEvent"] | S["LegacyToolCall"];
  finding_added: S["FindingAdded"] | S["LegacyFindingAdded"];
  chain_added: S["ChainAdded"] | S["LegacyChainAdded"];
  lopa_done: S["LopaDone"] | S["LegacyLopaDone"];
  evidence_added: S["EvidenceAdded"] | S["LegacyEvidenceAdded"];
  coverage_updated: { lines: CoverageLine[] };
  cap_hit: {
    reason: string;
    cap?: "analysis" | "post" | null;
    status?: string;
  };
  run_finished: S["RunFinished"] | S["LegacyRunFinished"];
  run_failed: S["RunFailed"];
  hypothesis_added: S["HypothesisAdded"] | S["LegacyHypothesisAdded"];
  hypothesis_dropped: S["HypothesisDropped"];
  run_extended: { step?: string; rerun_from?: string; evidence_only?: boolean };
  calculations_reattached: S["CalculationsReattached"];
};
export type EventType = keyof Payloads;

/** An event's payload as its type's model, or null for a payload the server marked invalid. */
export function payloadOf<T extends EventType>(
  event: ApiEvent,
  type: T,
): Payloads[T] | null {
  if (event.type !== type || event.payload_invalid) return null;
  return event.payload as Payloads[T];
}

// ---- tier chips ---------------------------------------------------------------------------

export type TierChip = {
  tier: S["Tier"] | null;
  /** "recorded" by the run; "inferred" on read for an event stored before v1.9 (C3) */
  source: "recorded" | "inferred" | null;
  text: string;
};

const TIER_NAMES: Record<S["Tier"], string> = {
  ultra: "Ultra",
  super: "Super",
  lightning: "Lightning",
  nano: "Nano",
};

/** The chip for a model call's or dispatch's tier, as the server sent it. */
export function tierChip(event: ApiEvent): TierChip | null {
  const p = payloadOf(event, "model_call") ?? payloadOf(event, "dispatch");
  if (p === null) return null;
  const tier = p.tier ?? null;
  const source = tier === null ? null : (p.tier_source ?? null);
  if (tier === null) return { tier, source, text: "unknown" };
  const name = TIER_NAMES[tier];
  return {
    tier,
    source,
    text: source === "inferred" ? `${name} (inferred)` : name,
  };
}

// ---- grouping -----------------------------------------------------------------------------

/** One step, `step_started` to `step_finished`, with what happened inside it. */
export type StepGroup = {
  kind: "step";
  seq: number;
  step: string;
  started: ApiEvent;
  finished: ApiEvent | null;
  /** decisions, dispatches, tool calls, hypotheses, chains, LOPA, evidence, caps: in order */
  rows: ApiEvent[];
  /** the step's model calls, grouped under its dispatch (or the step when it has none) */
  calls: ApiEvent[];
  /** findings added in the step: counted, listed when opened */
  findings: ApiEvent[];
};

/** An event outside any step: run started, extended, finished or failed; a stray event. */
export type LoneEvent = { kind: "event"; seq: number; event: ApiEvent };

export type TimelineItem = StepGroup | LoneEvent;

/** The timeline's items, in `seq` order. */
export function groupTimeline(events: readonly ApiEvent[]): TimelineItem[] {
  const items: TimelineItem[] = [];
  let open: StepGroup | null = null;
  for (const event of [...events].sort((a, b) => a.seq - b.seq)) {
    if (event.type === "step_started" && !event.payload_invalid) {
      const p = payloadOf(event, "step_started");
      open = {
        kind: "step",
        seq: event.seq,
        step: p?.step ?? "",
        started: event,
        finished: null,
        rows: [],
        calls: [],
        findings: [],
      };
      items.push(open);
    } else if (open !== null && event.type === "step_finished") {
      open.finished = event;
      open = null;
    } else if (open !== null && OUTSIDE_STEPS.has(event.type)) {
      open = null;
      items.push({ kind: "event", seq: event.seq, event });
    } else if (open !== null) {
      if (event.type === "model_call") open.calls.push(event);
      else if (event.type === "finding_added") open.findings.push(event);
      else open.rows.push(event);
    } else {
      items.push({ kind: "event", seq: event.seq, event });
    }
  }
  return items;
}

// these end any step left open: they belong to the run, not to a step (a `run_extended` can
// land inside a step that has started, so it stays in that step)
const OUTSIDE_STEPS: ReadonlySet<string> = new Set([
  "run_started",
  "run_finished",
  "run_failed",
  "calculations_reattached",
]);

/** Every event the timeline holds, in `seq` order (a test checks none is lost or added). */
export function eventsIn(items: readonly TimelineItem[]): ApiEvent[] {
  return items
    .flatMap((item) =>
      item.kind === "event"
        ? [item.event]
        : [
            item.started,
            ...item.rows,
            ...item.calls,
            ...item.findings,
            ...(item.finished ? [item.finished] : []),
          ],
    )
    .sort((a, b) => a.seq - b.seq);
}

// ---- side panel ---------------------------------------------------------------------------

/** The coverage bars: the latest `coverage_updated` lines, or none yet. */
export function latestCoverage(
  events: readonly ApiEvent[],
): CoverageLine[] | null {
  for (let n = events.length - 1; n >= 0; n--) {
    const p = payloadOf(events[n] as ApiEvent, "coverage_updated");
    if (p !== null) return p.lines;
  }
  return null;
}

export function findingsCount(events: readonly ApiEvent[]): number {
  return events.filter((e) => e.type === "finding_added").length;
}

/** What the run's model calls so far cost, from their events. */
export function spentSoFar(events: readonly ApiEvent[]): number {
  return events.reduce(
    (sum, e) => sum + (payloadOf(e, "model_call")?.cost_usd ?? 0),
    0,
  );
}

export type MixRow = {
  tier: S["Tier"] | "unknown";
  calls: number;
  cost_usd: number;
  /** of these calls, how many carry a tier inferred on read (C3) */
  inferred: number;
};

const MIX_ORDER: MixRow["tier"][] = [
  "ultra",
  "super",
  "lightning",
  "nano",
  "unknown",
];

/** Calls and cost per tier, from the `model_call` events: tiers with no call are left out. */
export function modelMix(events: readonly ApiEvent[]): MixRow[] {
  const rows = new Map<MixRow["tier"], MixRow>();
  for (const event of events) {
    const p = payloadOf(event, "model_call");
    const chip = tierChip(event);
    if (p === null || chip === null) continue;
    const tier = chip.tier ?? "unknown";
    const row = rows.get(tier) ?? { tier, calls: 0, cost_usd: 0, inferred: 0 };
    row.calls += 1;
    row.cost_usd += p.cost_usd;
    if (chip.source === "inferred") row.inferred += 1;
    rows.set(tier, row);
  }
  return MIX_ORDER.flatMap((t) => rows.get(t) ?? []);
}

// ---- end state ----------------------------------------------------------------------------

export type EndState = {
  kind:
    | "finished"
    | "analysis_cap"
    | "post_cap"
    | "cap"
    | "budget"
    | "failed"
    | "cancelled";
  text: string;
};

function lastOf<T extends EventType>(
  events: readonly ApiEvent[],
  type: T,
): Payloads[T] | null {
  for (let n = events.length - 1; n >= 0; n--) {
    const p = payloadOf(events[n] as ApiEvent, type);
    if (p !== null) return p;
  }
  return null;
}

/** How the run ended (Q10, J4), named by its status and its last `cap_hit.cap`, with spend
 * against that cap; null while it is still running. */
export function endState(
  run: Run,
  events: readonly ApiEvent[],
): EndState | null {
  const hit = lastOf(events, "cap_hit");
  const reason = hit ? ` ${hit.reason}.` : "";
  switch (run.status) {
    case "finished":
      return {
        kind: "finished",
        text: `Finished: spent ${money(run.spent_usd)}.`,
      };
    case "stopped_cap":
      if (hit?.cap === "analysis")
        return {
          kind: "analysis_cap",
          text: `Stopped at the analysis cap: ${money(run.cap_spent_usd)} of ${money(run.spend_cap_usd)} counted.${reason}`,
        };
      if (hit?.cap === "post")
        return {
          kind: "post_cap",
          text: `Stopped at the post cap of ${money(run.post_spend_cap_usd)}: spent ${money(run.spent_usd)} in all.${reason}`,
        };
      // an older run's cap_hit does not name its cap
      return {
        kind: "cap",
        text: `Stopped at a cap this run's events don't name: spent ${money(run.spent_usd)}.${reason}`,
      };
    case "stopped_budget":
      return {
        kind: "budget",
        text: `Stopped by the budget: spent ${money(run.spent_usd)}.${reason}`,
      };
    case "failed": {
      const failed = lastOf(events, "run_failed");
      const at = failed ? ` at the ${failed.step} step` : "";
      return {
        kind: "failed",
        text: `Failed${at}: spent ${money(run.spent_usd)}.`,
      };
    }
    case "cancelled":
      return {
        kind: "cancelled",
        text: `Cancelled: spent ${money(run.spent_usd)}.`,
      };
    default:
      return null;
  }
}

// ---- replay (P5-4) ------------------------------------------------------------------------

export type Speed = 1 | 10 | 60 | "max";
export const SPEEDS: readonly Speed[] = [1, 10, 60, "max"];

// a pause longer than this (a run left overnight, then resumed) plays as this, and the
// timeline says how long it really was
export const LONGEST_PAUSE_MS = 2000;
// at "max", one event per this
export const MAX_STEP_MS = 5;
// a gap this long is marked on the timeline
export const MARKED_GAP_MS = 10 * 60 * 1000;

function timeMs(event: ApiEvent): number {
  return Date.parse(event.time);
}

/** The wait before showing each event in a replay: the real gap from the one before, divided
 * by the speed, at most LONGEST_PAUSE_MS. The order is the events' own (`seq`). */
export function replayDelays(
  events: readonly ApiEvent[],
  speed: Speed,
): number[] {
  return events.map((event, n) => {
    if (n === 0) return 0;
    if (speed === "max") return MAX_STEP_MS;
    const gap = Math.max(0, timeMs(event) - timeMs(events[n - 1] as ApiEvent));
    return Math.min(gap / speed, LONGEST_PAUSE_MS);
  });
}

/** "23 h 40 min later" when this event came long after the one before, else null. */
export function gapBefore(
  events: readonly ApiEvent[],
  n: number,
): string | null {
  if (n <= 0) return null;
  const gap = timeMs(events[n] as ApiEvent) - timeMs(events[n - 1] as ApiEvent);
  if (gap < MARKED_GAP_MS) return null;
  const minutes = Math.round(gap / 60000);
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) return `${String(rest)} min later`;
  return rest === 0
    ? `${String(hours)} h later`
    : `${String(hours)} h ${String(rest)} min later`;
}
