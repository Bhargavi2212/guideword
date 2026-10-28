import { describe, expect, it } from "vitest";

import shortlistJson from "../../../contract/fixtures/shortlist.json";
import type { LopaRecord, Shortlist, ShortlistItem } from "../api/schema";
import { fixture } from "../test/fixtures";
import demoJson from "../test/fixtures/wg_demo_item.json";
import { must } from "../test/must";
import { chainFlow, factText, lopaBar } from "./visuals";

type Demo = {
  item: ShortlistItem;
  plant_detail: { facts: { id: string; value: unknown }[] };
};
const demo = demoJson as unknown as Demo;
const wg = demo.item;
const facts = Object.fromEntries(
  demo.plant_detail.facts.map((f) => [f.id, f.value]),
);
const mock = fixture<Shortlist>(shortlistJson);

describe("chainFlow (R4)", () => {
  const chain = must(wg.chain, "WG chain");
  const boxes = chainFlow(chain.links, facts, wg.evidence ?? []);

  it("gives one box per link, in the stored order, each traced to its link", () => {
    expect(boxes.map((b) => b.id)).toEqual(chain.links);
  });

  it("names each box by its tag or step", () => {
    expect(boxes[0]).toMatchObject({
      kind: "finding",
      name: "P-REB-START-2 early",
    });
    expect(boxes[2]).toMatchObject({
      kind: "fact",
      name: "HV-QW-B-IN normal position",
    });
  });

  it("shows each valve at its stored normal position, closed marked closed", () => {
    const valves = boxes.filter((b) => b.id.endsWith(".normal_position"));
    expect(valves).toHaveLength(4);
    for (const v of valves) {
      expect(v.value).toBe(facts[v.id]);
      expect(v.closed).toBe(facts[v.id] === "closed");
    }
    expect(
      boxes.find((b) => b.id === "EA-425B.design_pressure_kpa")?.closed,
    ).toBe(false);
  });

  it("writes a value with the unit its field name carries", () => {
    expect(
      boxes.find((b) => b.id === "EA-425B.design_pressure_kpa")?.value,
    ).toBe("2068 kPa(g)");
    expect(factText("X-1.boiling_point_c", -42)).toBe("-42 °C");
    expect(factText("X-1.vapor_pressure_kpaa", 101)).toBe("101 kPa(a)");
    expect(factText("RV-1.inlet_valve_ids", ["A", "B"])).toBe("A, B");
    expect(
      factText("E-1.heat_sources", [{ medium: "steam", via_line_id: "L-1" }]),
    ).toBe("steam");
    expect(factText("E-1.locked", true)).toBe("yes");
  });

  it("puts each calculation's result in the first box on its equipment", () => {
    const calc = must(
      (wg.evidence ?? []).find((e) => e.kind === "calculation"),
      "WG calculation",
    );
    const holder = boxes.filter((b) => b.calculations.length > 0);
    expect(holder.map((b) => b.id)).toEqual(["EA-425B.heat_sources"]);
    expect(holder[0]?.calculations).toEqual([
      { id: calc.id, verdict: calc.verdict, summary: calc.summary },
    ]);
  });

  it("shows no value for a link whose fact the plant doesn't hold", () => {
    expect(chainFlow(["Z-9.size_mm"], {}, [])[0]).toMatchObject({
      value: null,
      closed: false,
    });
  });
});

describe("lopaBar (R4)", () => {
  const lopa = must(wg.lopa, "WG LOPA");
  const credited: LopaRecord = {
    ...lopa,
    layers: [
      {
        layer_id: "BPCS-1",
        layer_type: "BPCS",
        credited: true,
        pfd: 0.1,
        reason: "credited",
      },
      ...(lopa.layers ?? []),
      {
        layer_id: "SIF-1",
        layer_type: "SIF",
        credited: true,
        pfd: 0.01,
        reason: "credited",
      },
    ],
    mitigated_frequency_per_year: 0.0001,
    gap: 1,
  };

  it("starts at the initiating frequency and ends at the stored mitigated one", () => {
    const bar = must(lopaBar(lopa));
    expect(bar.start).toEqual({ label: "IE-HE-MONTHLY", per_year: 0.1 });
    expect(bar.mitigated_per_year).toBe(0.1);
    expect(bar.tolerable_per_year).toBe(0.0001);
    expect(bar.gap).toBe(1000);
  });

  it("steps down by each credited layer's stored PFD; an uncredited one keeps its reason", () => {
    const bar = must(lopaBar(credited));
    expect(bar.steps.map((s) => [s.layer_id, s.credited, s.pfd])).toEqual([
      ["BPCS-1", true, 0.1],
      ["RV-PATH-EA425B", false, null],
      ["SIF-1", true, 0.01],
    ]);
    // only the log position is worked out: log10(start) plus each credited log10(PFD)
    expect(bar.steps.map((s) => s.log_after)).toEqual([-2, -2, -4]);
    expect(bar.steps[1]?.reason).toMatch(/^does not apply/);
  });

  it("puts the tolerable line where the served LOPA says, after an override too", () => {
    const overridden: LopaRecord = {
      ...lopa,
      severity_class: "S4",
      tolerable_per_year: 0.00001,
    };
    expect(must(lopaBar(overridden)).tolerable_per_year).toBe(0.00001);
    expect(must(lopaBar(overridden)).log_min).toBeLessThanOrEqual(-5);
  });

  it("spans the axis from the highest to the lowest frequency shown", () => {
    const bar = must(lopaBar(lopa));
    expect(bar.log_max).toBeGreaterThanOrEqual(-1);
    expect(bar.log_min).toBeLessThanOrEqual(-4);
  });

  it("draws every mock LOPA without a missing number", () => {
    for (const item of mock.items) {
      if (!item.lopa) continue;
      const bar = lopaBar(item.lopa);
      if (bar === null) continue;
      expect(Number.isFinite(bar.log_min) && Number.isFinite(bar.log_max)).toBe(
        true,
      );
    }
  });
});
