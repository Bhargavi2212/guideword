import { describe, expect, it } from "vitest";

import budgetJson from "../../../contract/fixtures/budget.json";
import type { Budget } from "../api/schema";
import { fixture } from "../test/fixtures";
import { startCheck } from "./runStart";

const budget = fixture<Budget>(budgetJson);
const live: Budget = { ...budget, live_run_available: true, message: null };

describe("startCheck (C6, C7, C13, G5–G7)", () => {
  it("adds the spend cap and the post cap into the maximum", () => {
    const check = startCheck(live, "development", "0.2", "0.1");
    expect(check.maximum).toBeCloseTo(0.3, 9);
    expect(check.refusals).toEqual([]);
  });

  it("shows the use's remaining amount and the phase's", () => {
    const check = startCheck(live, "video", "", "");
    expect(check.useLeft).toBe(2.0);
    expect(check.phase).toEqual(budget.api_run_phase);
  });

  it("refuses until both caps are entered: neither is ever pre-filled", () => {
    expect(startCheck(live, "development", "", "").refusals).toEqual([
      "Enter a spend cap.",
      "Enter a post cap.",
    ]);
    expect(startCheck(live, "development", "0", "0").refusals).toEqual([
      "The spend cap must be more than $0.",
    ]);
    expect(startCheck(live, "development", "0.1", "-1").refusals).toEqual([
      "The post cap can't be negative.",
    ]);
  });

  it("refuses a maximum over the phase's remaining amount, naming the phase", () => {
    expect(startCheck(live, "development", "0.4", "0.2").refusals).toEqual([
      "Up to $0.60 is more than phase 5 has left ($0.50).",
    ]);
  });

  it("refuses a maximum over the use's remaining amount, naming the use", () => {
    const spent: Budget = {
      ...live,
      uses: live.uses.map((u) =>
        u.use === "video" ? { ...u, spent_usd: 1.9, remaining_usd: 0.1 } : u,
      ),
    };
    expect(startCheck(spent, "video", "0.1", "0.1").refusals).toEqual([
      "Up to $0.20 is more than the video use has left ($0.10).",
    ]);
  });

  it("refuses a use this environment has no allowance for", () => {
    const hosted: Budget = {
      ...live,
      uses: live.uses.filter((u) => u.use !== "development"),
    };
    const check = startCheck(hosted, "development", "0.1", "0.1");
    expect(check.useLeft).toBeNull();
    expect(check.refusals).toEqual([
      "The development use has no allowance in this environment.",
    ]);
  });

  it("refuses everything when live runs are off, with the server's reason", () => {
    expect(startCheck(budget, "development", "0.1", "0.1").refusals).toEqual([
      "Mock mode: no live runs.",
    ]);
  });
});
