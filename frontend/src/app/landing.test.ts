import { describe, expect, it } from "vitest";

import demoJson from "../../../contract/fixtures/demo_response.json";
import type { DemoResponse } from "../api/schema";
import { fixture } from "../test/fixtures";
import { landingRoute, startTarget } from "./landing";

const demo = fixture<DemoResponse>(demoJson);
const RUN = demo.run.run.id;

describe("the landing (deploy plan D3)", () => {
  it.each(["", "#", "#/"])("opens the demo run's shortlist from %j", (hash) => {
    expect(landingRoute(hash, demo)).toEqual({ name: "shortlist", runId: RUN });
  });

  it("leaves any other hash alone", () => {
    expect(landingRoute("#/plants", demo)).toBeNull();
    expect(
      landingRoute(`#/runs/${encodeURIComponent(RUN)}/coverage`, demo),
    ).toBeNull();
  });

  it("does nothing without a demo", () => {
    expect(landingRoute("", null)).toBeNull();
  });
});

describe("the start line", () => {
  it("is the run's own entry's, on that run only (contract v1.11)", () => {
    const runs = demo.runs.map((r) => ({ ...r, start_target_id: "ch:x" }));
    const named = { ...demo, start_target_id: "ch:x", runs };
    expect(startTarget(named, RUN)).toBe("ch:x");
    expect(startTarget(named, "run:other")).toBeNull();
    expect(startTarget({ ...demo, start_target_id: null }, RUN)).toBeNull();
    expect(startTarget(null, RUN)).toBeNull();
  });

  it("falls back to the response's own start line before v1.11 (no runs list)", () => {
    const older = { ...demo, start_target_id: "ch:x", runs: [] };
    expect(startTarget(older, RUN)).toBe("ch:x");
    expect(startTarget(older, "run:other")).toBeNull();
  });
});
