import { describe, expect, it } from "vitest";

import shortlistJson from "../../../contract/fixtures/shortlist.json";
import type { Shortlist, ShortlistItem } from "../api/schema";
import { fixture } from "../test/fixtures";
import { must } from "../test/must";
import { gapWords, lineTags, lopaLine, severityText } from "./technical";

const data = fixture<Shortlist>(shortlistJson);
const items = data.items;

function item(prefix: string): ShortlistItem {
  return must(items.find((i) => i.target_id.startsWith(prefix)));
}

describe("the gap as the engineer reads it (review plan Q10)", () => {
  it("is N times over the risk limit, to two significant figures", () => {
    expect(gapWords(item("f:pair:"))).toBe("1,000× over the risk limit");
    expect(gapWords(item("ch:"))).toBe("100× over the risk limit");
    expect(gapWords(item("f:m:S-MX-1:more:temperature"))).toBe(
      "10× over the risk limit",
    );
  });

  it("is within the limit at or under 1, unknown when the LOPA is incomplete, else none", () => {
    const pair = item("f:pair:");
    expect(gapWords({ ...pair, gap: 1 })).toBe("within the risk limit");
    expect(gapWords({ ...pair, gap: 0.04 })).toBe("within the risk limit");
    expect(gapWords({ ...pair, gap: 2.345 })).toBe("2.3× over the risk limit");
    expect(gapWords(item("f:m:S-L-12:reverse:flow"))).toBe(
      "gap unknown: the LOPA is incomplete",
    );
    expect(gapWords(item("h:"))).toBe("no LOPA");
  });
});

describe("the LOPA line", () => {
  it("names the initiating event, the credit, and mitigated against tolerable", () => {
    expect(lopaLine(must(item("ch:").lopa))).toBe(
      "initiating event IE-HE-MONTHLY at 0.1 /yr · 1 of 2 layers credited · mitigated 0.01 /yr against tolerable 1e-4 /yr",
    );
  });

  it("says what is missing when the frequency is unknown", () => {
    expect(lopaLine(must(item("f:m:S-L-12:reverse:flow").lopa))).toBe(
      "initiating event IE-PIPE-LEAK-S at — · 0 of 0 layers credited · mitigated — against tolerable 1e-5 /yr",
    );
  });
});

describe("the severity code with the table's own definition", () => {
  it("reads code, name and definition from the shortlist's severity classes", () => {
    expect(severityText("S1", data.severity_classes)).toBe(
      "S1 Minor: First aid or minor injury on site; small release contained on site",
    );
  });

  it("shows the code alone when the table doesn't have it", () => {
    expect(severityText("S9", data.severity_classes)).toBe("S9");
  });
});

describe("the tags a line names", () => {
  it("are a finding's failing components", () => {
    const pair = item("f:pair:");
    expect(lineTags(pair)).toEqual(pair.finding?.failing_component_ids);
  });

  it("are a chain's fact objects and its findings' objects, each once", () => {
    const chain = item("ch:");
    const tags = lineTags(chain);
    expect(tags).toContain("MX-1");
    expect(tags).toContain("XV-STM");
    expect(new Set(tags).size).toBe(tags.length);
    expect(tags.every((t) => !t.includes(":") && !t.includes("."))).toBe(true);
  });

  it("are a hypothesis's components", () => {
    const h = item("h:");
    expect(lineTags(h)).toEqual(h.hypothesis?.component_ids);
  });
});
