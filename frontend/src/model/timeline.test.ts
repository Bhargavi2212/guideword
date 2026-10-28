import { describe, expect, it } from "vitest";

import pageJson from "../../../contract/fixtures/events_page.json";
import failedJson from "../../../contract/fixtures/events_page_failed.json";
import phase2Json from "../../../contract/fixtures/legacy/events_phase2.json";
import phase3Json from "../../../contract/fixtures/legacy/events_phase3.json";
import phase4Json from "../../../contract/fixtures/legacy/events_phase4.json";
import otherJson from "../../../contract/fixtures/legacy/events_other_shapes.json";
import runJson from "../../../contract/fixtures/run_detail.json";
import type { EventsPage, Run, RunDetail } from "../api/schema";
import { fixture } from "../test/fixtures";
import {
  LONGEST_PAUSE_MS,
  MAX_STEP_MS,
  endState,
  eventLine,
  eventsIn,
  findingsCount,
  gapBefore,
  groupTimeline,
  latestCoverage,
  modelMix,
  recordIdOf,
  replayDelays,
  spentSoFar,
  tierChip,
  type ApiEvent,
} from "./timeline";

const page = fixture<EventsPage>(pageJson).events;
const failed = fixture<EventsPage>(failedJson).events;
// the legacy files hold stored events as the store keeps them, before any tier is added on read
const legacy = (json: unknown) => (json as { events: ApiEvent[] }).events;
const other = (
  otherJson as unknown as { events: { event: ApiEvent }[] }
).events.map((e) => e.event);
const LEGACY: [string, ApiEvent[]][] = [
  ["phase 2", legacy(phase2Json)],
  ["phase 3", legacy(phase3Json)],
  ["phase 4", legacy(phase4Json)],
  ["other shapes", other],
];
const run = fixture<RunDetail>(runJson).run;

const seqs = (events: readonly ApiEvent[]) => events.map((e) => e.seq);
const sorted = (events: readonly ApiEvent[]) =>
  seqs(events).sort((a, b) => a - b);

/** The server's tier on read for a stored event (C3), as `live.events` adds it. */
function inferred(event: ApiEvent, tier: string | null): ApiEvent {
  return {
    ...event,
    payload: {
      ...(event.payload as object),
      tier,
      tier_source: tier === null ? null : "inferred",
    },
  } as ApiEvent;
}

describe("groupTimeline", () => {
  const all: [string, ApiEvent[]][] = [
    ["v1.9", page],
    ["failed (H3)", failed],
    ...LEGACY,
  ];

  it.each(all)("holds every %s event once, in seq order", (_, events) => {
    expect(seqs(eventsIn(groupTimeline(events)))).toEqual(sorted(events));
  });

  it("gives one group per step, each closed by its own step_finished", () => {
    const items = groupTimeline(page);
    const steps = items.filter((i) => i.kind === "step");
    expect(steps).toHaveLength(
      page.filter((e) => e.type === "step_started").length,
    );
    for (const step of steps) {
      expect(step.finished?.type).toBe("step_finished");
      expect((step.finished?.payload as { step: string }).step).toBe(step.step);
    }
  });

  it("puts each model call and finding under its step, and the run's events outside", () => {
    const items = groupTimeline(page);
    const calls = items.flatMap((i) => (i.kind === "step" ? i.calls : []));
    expect(calls).toHaveLength(
      page.filter((e) => e.type === "model_call").length,
    );
    expect(calls.every((e) => e.type === "model_call")).toBe(true);
    const findings = items.flatMap((i) =>
      i.kind === "step" ? i.findings : [],
    );
    expect(findings).toHaveLength(findingsCount(page));
    expect(items[0]).toMatchObject({
      kind: "event",
      event: { type: "run_started" },
    });
    expect(items.at(-1)).toMatchObject({
      kind: "event",
      event: { type: "run_finished" },
    });
    const lone = items.flatMap((i) =>
      i.kind === "event" ? [i.event.type] : [],
    );
    expect(lone).toContain("run_extended");
  });

  it("ends a failed run on its run_failed", () => {
    expect(groupTimeline(failed).at(-1)).toMatchObject({
      kind: "event",
      event: { type: "run_failed" },
    });
  });

  it("keeps the dispatch among the step's rows, after the calls it sent", () => {
    const step = groupTimeline(page).find(
      (i) => i.kind === "step" && i.rows.some((r) => r.type === "dispatch"),
    );
    expect(step?.kind).toBe("step");
    if (step?.kind !== "step") return;
    const dispatch = step.rows.find((r) => r.type === "dispatch");
    expect(step.calls.every((c) => c.seq < (dispatch?.seq ?? 0))).toBe(true);
  });
});

describe("tier chips (C3)", () => {
  const call = page.find((e) => e.type === "model_call") as ApiEvent;
  const storedCall = legacy(phase4Json).find(
    (e) => e.type === "model_call",
  ) as ApiEvent;
  const storedDispatch = legacy(phase4Json).find(
    (e) => e.type === "dispatch",
  ) as ApiEvent;

  it("shows the tier a v1.9 run recorded", () => {
    const tier = (call.payload as { tier: string }).tier;
    expect(tierChip(call)).toMatchObject({ tier, source: "recorded" });
    expect(tierChip(call)?.text).not.toContain("inferred");
  });

  it("shows a tier inferred on read as inferred", () => {
    expect(tierChip(inferred(storedCall, "lightning"))).toEqual({
      tier: "lightning",
      source: "inferred",
      text: "Lightning (inferred)",
    });
    expect(tierChip(inferred(storedDispatch, "super"))?.text).toBe(
      "Super (inferred)",
    );
  });

  it("shows a tier nobody knows as unknown", () => {
    expect(tierChip(inferred(storedCall, null))?.text).toBe("unknown");
    // a stored event read with no tier at all
    expect(tierChip(storedCall)?.text).toBe("unknown");
  });

  it("gives no chip to an event that has no tier", () => {
    expect(tierChip(page[0] as ApiEvent)).toBeNull();
  });
});

describe("the side panel", () => {
  it("counts calls and cost per tier from the model_call events", () => {
    const mix = modelMix(page);
    const calls = page.filter((e) => e.type === "model_call");
    expect(mix.reduce((n, r) => n + r.calls, 0)).toBe(calls.length);
    for (const row of mix) {
      const mine = calls.filter(
        (e) =>
          ((e.payload as { tier: string | null }).tier ?? "unknown") ===
          row.tier,
      );
      expect(row.calls).toBe(mine.length);
      expect(row.cost_usd).toBeCloseTo(
        mine.reduce(
          (s, e) => s + (e.payload as { cost_usd: number }).cost_usd,
          0,
        ),
        9,
      );
      expect(row.inferred).toBe(0);
    }
    expect(spentSoFar(page)).toBeCloseTo(
      mix.reduce((s, r) => s + r.cost_usd, 0),
      9,
    );
  });

  it("counts inferred and unknown tiers apart", () => {
    const stored = legacy(phase4Json).filter((e) => e.type === "model_call");
    const mix = modelMix([
      inferred(stored[0] as ApiEvent, "ultra"),
      inferred(stored[0] as ApiEvent, null),
    ]);
    expect(mix.map((r) => [r.tier, r.calls, r.inferred])).toEqual([
      ["ultra", 1, 1],
      ["unknown", 1, 0],
    ]);
  });

  it("shows the latest coverage lines, and none before the first update", () => {
    const updates = page.filter((e) => e.type === "coverage_updated");
    expect(latestCoverage(page)).toEqual(
      (updates.at(-1)?.payload as { lines: unknown }).lines,
    );
    expect(latestCoverage(page.slice(0, 2))).toBeNull();
  });
});

describe("endState (Q10, J4)", () => {
  const capHit = (cap: "analysis" | "post" | null): ApiEvent =>
    ({
      ...(page.find((e) => e.type === "cap_hit") as ApiEvent),
      payload: { reason: "limit reached", cap, status: "stopped_cap" },
    }) as ApiEvent;
  const as = (status: Run["status"]): Run => ({ ...run, status });

  it("names each way a run ends, with spend against that cap", () => {
    expect(endState(as("finished"), page)).toEqual({
      kind: "finished",
      text: "Finished: spent <$0.01.",
    });
    expect(endState(as("stopped_cap"), [capHit("analysis")])?.text).toBe(
      "Stopped at the analysis cap: <$0.01 of $0.20 counted. limit reached.",
    );
    expect(endState(as("stopped_cap"), [capHit("post")])?.text).toBe(
      "Stopped at the post cap of $0.10: spent <$0.01 in all. limit reached.",
    );
    expect(endState(as("stopped_budget"), [capHit(null)])?.kind).toBe("budget");
    expect(endState(as("cancelled"), [])?.kind).toBe("cancelled");
  });

  it("names the step a failed run failed at", () => {
    expect(endState(as("failed"), failed)?.text).toBe(
      "Failed at the analysis step: spent <$0.01.",
    );
  });

  it("says when an older run's cap_hit doesn't name its cap", () => {
    expect(endState(as("stopped_cap"), legacy(phase2Json))?.kind).toBe("cap");
  });

  it("is null while the run is running", () => {
    expect(endState(as("running"), page)).toBeNull();
  });
});

describe("replay timing (P5-4)", () => {
  it("waits the real gap divided by the speed, never longer than the longest pause", () => {
    const times = page.map((e) => Date.parse(e.time));
    const delays = replayDelays(page, 10);
    expect(delays).toHaveLength(page.length);
    expect(delays[0]).toBe(0);
    for (let n = 1; n < page.length; n++)
      expect(delays[n]).toBe(
        Math.min(
          ((times[n] ?? 0) - (times[n - 1] ?? 0)) / 10,
          LONGEST_PAUSE_MS,
        ),
      );
  });

  it("steps evenly at max", () => {
    expect(new Set(replayDelays(page, "max").slice(1))).toEqual(
      new Set([MAX_STEP_MS]),
    );
  });

  it("marks a long pause with how long it really was", () => {
    const events = legacy(phase3Json);
    const marks = events
      .map((_, n) => gapBefore(events, n))
      .filter((g) => g !== null);
    expect(marks.length).toBeGreaterThan(0);
    for (const mark of marks)
      expect(mark).toMatch(/^(\d+ h )?(\d+ min )?later$/);
    expect(gapBefore(page, 1)).toBeNull();
  });
});

describe("eventLine and recordIdOf", () => {
  const first = (events: readonly ApiEvent[], type: string) =>
    events.find((e) => e.type === type) as ApiEvent;

  it("says what each kind of event did, in one line", () => {
    expect(eventLine(first(page, "run_started"))).toBe(
      "Run started: attempt 1, 98 questions in 9 sections",
    );
    expect(eventLine(first(page, "dispatch"))).toMatch(
      /^Dispatch to chemistry \(bulk\): 7 questions, selected by code/,
    );
    expect(eventLine(first(page, "hypothesis_dropped"))).toBe(
      "Hypothesis #3 dropped: rank 3: TANK-9 not in this plant",
    );
    expect(eventLine(first(page, "cap_hit"))).toBe(
      "Post cap hit: run run:eaf6f55e4d2a4a30 limit $0.00 would be exceeded",
    );
    expect(eventLine(first(page, "run_finished"))).toBe(
      "Run finished: spent <$0.01",
    );
    expect(eventLine(first(failed, "run_failed"))).toBe(
      "Run failed at the analysis step",
    );
  });

  it("gives every event of every fixture a line", () => {
    for (const events of [page, failed, ...LEGACY.map(([, e]) => e)])
      for (const event of events) expect(eventLine(event)).not.toBe("");
  });

  it("names a payload the server could not read", () => {
    const bad = {
      ...(page[0] as ApiEvent),
      payload: {},
      payload_invalid: true,
      payload_error: "missing attempt",
    } as ApiEvent;
    expect(eventLine(bad)).toBe(
      "run_started: payload not readable (missing attempt)",
    );
  });

  it("links an event to the record it made", () => {
    expect(recordIdOf(first(page, "finding_added"))).toBe(
      (first(page, "finding_added").payload as { finding_id: string })
        .finding_id,
    );
    expect(recordIdOf(first(page, "model_call"))).toMatch(/^mc:/);
    expect(recordIdOf(first(page, "run_started"))).toBeNull();
  });
});
