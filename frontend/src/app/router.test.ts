import { describe, expect, it } from "vitest";

import { buildHash, parseHash, type Route } from "./router";

const RUN = "run:76f8ee0b5d1f078e";
const CHAIN =
  "ch:EA-425B.design_pressure_kpa+EA-425B.heat_sources+f:proc:P-REB-START-2:early";
const PLANT = "plant:mock_plant_a:be40872ede387491";
const SPLIT = "S-L-12~P-1";

const ROUTES: Route[] = [
  { name: "plants" },
  { name: "plant", plantId: PLANT },
  { name: "sections", plantId: PLANT },
  { name: "runs" },
  { name: "live", runId: RUN },
  { name: "shortlist", runId: RUN },
  { name: "item", runId: RUN, targetId: CHAIN },
  { name: "item", runId: `${RUN}:2`, targetId: SPLIT },
  { name: "worksheet", runId: RUN },
  { name: "coverage", runId: RUN },
];

describe("router", () => {
  it.each(ROUTES)("builds and parses $name", (route) => {
    expect(parseHash(buildHash(route))).toEqual(route);
  });

  it("encodes IDs so `:`, `~`, `+` and `/` survive", () => {
    const hash = buildHash({ name: "item", runId: RUN, targetId: CHAIN });
    expect(hash).toBe(
      `#/runs/${encodeURIComponent(RUN)}/items/${encodeURIComponent(CHAIN)}`,
    );
    expect(hash).not.toContain("+");
  });

  it("reads the empty hash as the plant list", () => {
    expect(parseHash("")).toEqual({ name: "plants" });
    expect(parseHash("#/")).toEqual({ name: "plants" });
  });

  it("reads an unknown path as not found, keeping what was asked", () => {
    expect(parseHash("#/nowhere/x")).toEqual({
      name: "not_found",
      path: "/nowhere/x",
    });
    expect(parseHash("#/runs/x/elsewhere")).toEqual({
      name: "not_found",
      path: "/runs/x/elsewhere",
    });
  });

  it("reads a badly encoded ID as not found rather than throwing", () => {
    expect(parseHash("#/runs/%E0%A4%A/shortlist").name).toBe("not_found");
  });
});
