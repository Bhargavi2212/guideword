// The shortlist as cards (spec 5.1): pure functions, no formatting of any number. The server
// orders the lines (R50: tiers, then the hypothesis rank or the gap); nothing here re-sorts.

import type { ShortlistEvidence, ShortlistItem } from "../api/schema";
import { handleFlag, unresolvedHandles } from "./names";

export type Tier = ShortlistItem["tier"];
export const TIERS: readonly Tier[] = [
  "confirmed",
  "also_found",
  "unconfirmed",
];
export const TIER_TITLES: Record<Tier, string> = {
  confirmed: "Confirmed",
  also_found: "Also found",
  unconfirmed: "Unconfirmed",
};
// a card shows up to this many evidence records (spec 5.1)
export const EVIDENCE_SHOWN = 3;

export type TierGroup = { tier: Tier; title: string; items: ShortlistItem[] };

/** The three tiers in order, each with its items in the server's order (never re-sorted). */
export function groupByTier(items: readonly ShortlistItem[]): TierGroup[] {
  return TIERS.map((tier) => ({
    tier,
    title: TIER_TITLES[tier],
    items: items.filter((item) => item.tier === tier),
  }));
}

/** The card's lead: a finding's consequence, a chain's description, or a hypothesis's mechanism. */
export function leadText(item: ShortlistItem): string {
  return (
    item.finding?.consequence ??
    item.chain?.description ??
    item.hypothesis?.mechanism ??
    ""
  );
}

/** The line's severity class, from its chain or its finding; a hypothesis has none. */
export function severityOf(item: ShortlistItem): string | null {
  return item.chain?.severity_class ?? item.finding?.severity_class ?? null;
}

export function shownEvidence(item: ShortlistItem): ShortlistEvidence[] {
  return (item.evidence ?? []).slice(0, EVIDENCE_SHOWN);
}

/** A chain's handle flag, when its own words keep the chain-finder's handles (row 251). */
export function chainHandleFlag(item: ShortlistItem): string | null {
  const chain = item.chain;
  if (!chain) return null;
  return handleFlag(unresolvedHandles([chain.description, chain.reason ?? ""]));
}
