import { describe, expect, it } from "vitest";

import shortlistJson from "../../../contract/fixtures/shortlist.json";
import type { Evidence, Shortlist } from "../api/schema";
import { fixture } from "../test/fixtures";
import { must } from "../test/must";
import {
  calculationOf,
  CALCULATION_NAMES,
  isSkipped,
  shownFlag,
  skippedLine,
} from "./evidence";

const items = fixture<Shortlist>(shortlistJson).items;
const evidence = items.flatMap((i) => i.evidence ?? []);
const skipped = must(
  evidence.find((e) => e.kind === "calculation" && e.verdict === "none"),
);
const confirmed = must(
  evidence.find((e) => e.kind === "calculation" && e.verdict === "confirmed"),
);

function card(over: Partial<Evidence>): Evidence {
  return { ...skipped, ...over };
}

describe("calculationOf (PROJECT.md §11 evidence ID form)", () => {
  it("reads the calculation and its equipment from a calculation card's ID", () => {
    expect(calculationOf(skipped)).toEqual({
      calculation: "blocked_in_heating",
      equipment_id: "MX-1",
    });
    expect(calculationOf(confirmed)?.calculation).toBe("heat_up_rate");
  });

  it("keeps a hyphen in the equipment ID", () => {
    const id =
      "ev:f:m:S-EA-425B:more:temperature:super:C22:e5:calculation:heat_up_rate-EA-425B";
    expect(calculationOf(card({ id }))).toEqual({
      calculation: "heat_up_rate",
      equipment_id: "EA-425B",
    });
  });

  it("gives null for a precedent card", () => {
    const precedent = must(evidence.find((e) => e.kind === "precedent"));
    expect(calculationOf(precedent)).toBeNull();
  });

  it("names every calculation the backend writes", () => {
    expect(Object.keys(CALCULATION_NAMES).sort()).toEqual([
      "blocked_in_heating",
      "heat_up_rate",
      "overflow_time",
    ]);
  });
});

describe("a skipped calculation", () => {
  it("is a calculation card with missing facts", () => {
    expect(isSkipped(skipped)).toBe(true);
    expect(isSkipped(confirmed)).toBe(false);
    expect(isSkipped(card({ kind: "precedent" }))).toBe(false);
  });

  it("reads as one line: the calculation and how many plant facts are missing", () => {
    expect(skippedLine(skipped)).toBe(
      "Blocked-in heating check skipped: 3 plant facts missing",
    );
    const eleven = Array.from({ length: 11 }, (_, n) => `EA-425B.f${n}`);
    const id = "ev:f:x:calculation:heat_up_rate-EA-425B";
    expect(skippedLine(card({ id, missing_fact_ids: eleven }))).toBe(
      "Heat-up time skipped: 11 plant facts missing",
    );
    expect(skippedLine(card({ missing_fact_ids: ["MX-1.volume_m3"] }))).toBe(
      "Blocked-in heating check skipped: 1 plant fact missing",
    );
  });
});

describe("shownFlag", () => {
  it("gives the skip flag as a count, not the list again", () => {
    const flag = must(
      items
        .flatMap((i) => i.flags ?? [])
        .find((f) => f.startsWith("evidence skipped")),
    );
    expect(shownFlag(flag)).toBe("evidence skipped: 3 plant facts missing");
  });

  it("leaves every other flag verbatim", () => {
    const other =
      "unexpected character in model text: U+4E92 (chain description)";
    expect(shownFlag(other)).toBe(other);
  });
});
