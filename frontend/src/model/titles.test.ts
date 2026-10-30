import { describe, expect, it } from "vitest";

import shortlistJson from "../../../contract/fixtures/shortlist.json";
import type { Shortlist, ShortlistItem } from "../api/schema";
import { fixture } from "../test/fixtures";
import { must } from "../test/must";
import { TEMPLATES, findingQuestion, lineTitle, questionTitle } from "./titles";

const items = fixture<Shortlist>(shortlistJson).items;

describe("one plain title per line kind, written in code (review plan R3)", () => {
  it.each([
    ["m:S-EA-425B:more:pressure", "More pressure at EA-425B"],
    [
      "m:S-L-QW-B-IN:other_than:composition",
      "Other than composition at L-QW-B-IN",
    ],
    ["m:S-L-RUNDOWN~E-106:no:flow", "No flow at L-RUNDOWN (E-106)"],
    ["proc:P-REB-START-2:early", "Step P-REB-START-2 done too early"],
    ["proc:P-1:skipped", "Step P-1 skipped"],
    ["proc:P-1:out_of_order", "Step P-1 done out of order"],
    ["pair:PROPANE:WATER", "PROPANE and WATER mix"],
    ["env:C4-HEAVIES:water", "C4-HEAVIES meets water"],
    ["nf:L-RUNDOWN", "No flow in line L-RUNDOWN"],
    ["work:W-1:EA-425B", "Planned work W-1 on EA-425B"],
    ["dust:SILO-1", "Dust at SILO-1"],
    ["relief:PSV-1", "Where PSV-1 discharges"],
    ["ai:S-MX-1:aaaaaaaaaaaaaaaa", "Question added by the analysis on MX-1"],
    ["eng:S-MX-1:aaaaaaaaaaaaaaaa", "Engineer's question on MX-1"],
  ])("%s reads %s", (question, title) => {
    expect(questionTitle(question)).toBe(title);
  });

  it("reads the question back out of a finding ID", () => {
    expect(
      findingQuestion("f:proc:P-REB-START-2:early:super:C16:126a45a4b13afa1b"),
    ).toBe("proc:P-REB-START-2:early");
    expect(
      findingQuestion("f:m:S-EA-425B:more:pressure:super:C22:e53bce019995581b"),
    ).toBe("m:S-EA-425B:more:pressure");
  });

  it("gives every line in the fixture a title, and no raw key in it", () => {
    for (const item of items) {
      const title = lineTitle(item);
      expect(title.length).toBeGreaterThan(0);
      expect(title).not.toMatch(/\b(?:f|m|ch|proc|pair|env|hyp):/);
    }
  });

  it("titles a chain by its finding links", () => {
    const chain = must(items.find((i) => i.target_kind === "chain"));
    const title = lineTitle(chain);
    const findings = (chain.chain?.links ?? []).filter((l) =>
      l.startsWith("f:"),
    );
    expect(title.startsWith(`${findings.length} failures together: `)).toBe(
      true,
    );
  });

  it("names a repeated question once in a chain's title (D #6)", () => {
    const chain = must(items.find((i) => i.target_kind === "chain"));
    const twice = "f:m:S-L-RUNDOWN:more:pressure:super:C01:0123456789abcdef";
    const again = "f:m:S-L-RUNDOWN:more:pressure:super:C02:fedcba9876543210";
    const item = {
      ...chain,
      chain: {
        ...must(chain.chain),
        links: [twice, "V-1.normal_position", again],
      },
    };
    const one = questionTitle(findingQuestion(twice));
    expect(lineTitle(item)).toBe(`2 failures together: ${one}`);
  });

  it("titles a hypothesis by its rank", () => {
    const item = must(items.find((i) => i.target_kind === "hypothesis"));
    expect(lineTitle(item)).toBe(
      `Whole-plant hypothesis #${String(item.hypothesis?.rank)}`,
    );
  });

  it("lists every template string, so the PR can show them", () => {
    expect(Object.keys(TEMPLATES).sort()).toEqual(
      [
        "ai",
        "chain",
        "dust",
        "eng",
        "env",
        "hypothesis",
        "m",
        "nf",
        "pair",
        "proc",
        "relief",
        "work",
      ].sort(),
    );
  });

  it("an unknown question kind still gets a plain title, never a key", () => {
    const first = must(items.find((i) => i.target_kind === "finding"));
    const odd = { ...first, target_kind: "finding" } as ShortlistItem;
    const finding = { ...must(odd.finding), question_id: "zz:X:y" };
    expect(lineTitle({ ...odd, finding })).toBe("X y");
  });
});
