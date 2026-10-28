// The start form's check (spec 5.3, P5-8; C6, C7, C13, G5–G7): the maximum a run can spend is
// its spend cap plus its post cap, and Start is refused, with the reason, while either cap is
// missing or the maximum is more than the use's or the phase's remaining amount. The server
// makes the same check (B2); this one only says why before anything is sent.

import type { Budget } from "../api/schema";
import { money } from "../format/number";

export type BudgetUseName = Budget["api_run_uses"][number];

export type StartCheck = {
  /** spend cap + post cap, once both are numbers */
  maximum: number | null;
  /** this use's remaining amount in this environment; null when it has none here */
  useLeft: number | null;
  phase: Budget["api_run_phase"];
  refusals: string[];
};

function amount(text: string): number | null {
  if (text.trim() === "") return null;
  const value = Number(text);
  return Number.isFinite(value) ? value : null;
}

export function startCheck(
  budget: Budget,
  use: BudgetUseName,
  spendCapText: string,
  postCapText: string,
): StartCheck {
  const phase = budget.api_run_phase;
  const useLeft = budget.uses.find((u) => u.use === use)?.remaining_usd ?? null;
  if (!budget.live_run_available) {
    const why = budget.message ?? "Live runs are off here.";
    return { maximum: null, useLeft, phase, refusals: [why] };
  }
  const spend = amount(spendCapText);
  const post = amount(postCapText);
  const refusals: string[] = [];
  if (spend === null) refusals.push("Enter a spend cap.");
  else if (spend <= 0) refusals.push("The spend cap must be more than $0.");
  if (post === null) refusals.push("Enter a post cap.");
  else if (post < 0) refusals.push("The post cap can't be negative.");
  const maximum = spend !== null && post !== null ? spend + post : null;
  if (useLeft === null) {
    refusals.push(`The ${use} use has no allowance in this environment.`);
  } else if (refusals.length === 0 && maximum !== null) {
    if (maximum > useLeft)
      refusals.push(
        `Up to ${money(maximum)} is more than the ${use} use has left (${money(useLeft)}).`,
      );
    if (maximum > phase.remaining_usd)
      refusals.push(
        `Up to ${money(maximum)} is more than phase ${phase.phase} has left (${money(phase.remaining_usd)}).`,
      );
  }
  return { maximum, useLeft, phase, refusals };
}
