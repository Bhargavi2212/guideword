import { describe, expect, it } from "vitest";

import shortlistJson from "../../../contract/fixtures/shortlist.json";
import type { Shortlist, ShortlistItem } from "../api/schema";
import { fixture } from "../test/fixtures";
import {
  EVIDENCE_SHOWN,
  groupByTier,
  leadText,
  severityOf,
  shownEvidence,
} from "./shortlist";

const items = fixture<Shortlist>(shortlistJson).items;

describe("groupByTier", () => {
  it("gives the three tiers in order, each as the server ordered it", () => {
    const groups = groupByTier(items);
    expect(groups.map((g) => g.tier)).toEqual([
      "confirmed",
      "also_found",
      "unconfirmed",
    ]);
    for (const group of groups) {
      expect(group.items.map((i) => i.target_id)).toEqual(
        items.filter((i) => i.tier === group.tier).map((i) => i.target_id),
      );
    }
  });

  it("never re-sorts: an order that disagrees with the ranks is kept as served", () => {
    const reversed = [...items].reverse();
    const groups = groupByTier(reversed);
    expect(groups[1]?.items.map((i) => i.target_id)).toEqual(
      reversed.filter((i) => i.tier === "also_found").map((i) => i.target_id),
    );
  });

  it("keeps an empty tier, so the three headings always show", () => {
    const groups = groupByTier(items.filter((i) => i.tier !== "unconfirmed"));
    expect(groups.map((g) => [g.tier, g.items.length])).toEqual([
      ["confirmed", 2],
      ["also_found", 3],
      ["unconfirmed", 0],
    ]);
  });
});

describe("a card's words", () => {
  const byKind = (kind: ShortlistItem["target_kind"]) =>
    items.find((i) => i.target_kind === kind) as ShortlistItem;

  it("leads with the finding's consequence, the chain's description or the mechanism", () => {
    expect(leadText(byKind("finding"))).toBe(
      byKind("finding").finding?.consequence,
    );
    expect(leadText(byKind("chain"))).toBe(byKind("chain").chain?.description);
    expect(leadText(byKind("hypothesis"))).toBe(
      byKind("hypothesis").hypothesis?.mechanism,
    );
  });

  it("takes the severity from the chain or the finding", () => {
    expect(severityOf(byKind("chain"))).toBe(
      byKind("chain").chain?.severity_class,
    );
    expect(severityOf(byKind("finding"))).toBe(
      byKind("finding").finding?.severity_class,
    );
    expect(severityOf(byKind("hypothesis"))).toBeNull();
  });

  it("shows at most three evidence records, in the server's order", () => {
    const many = items.flatMap((i) => i.evidence ?? []);
    expect(many.length).toBeGreaterThan(EVIDENCE_SHOWN);
    const item = { ...byKind("finding"), evidence: many };
    expect(shownEvidence(item).map((e) => e.id)).toEqual(
      many.slice(0, EVIDENCE_SHOWN).map((e) => e.id),
    );
  });
});
