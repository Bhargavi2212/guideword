import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import budgetJson from "../../../contract/fixtures/budget.json";
import plantsJson from "../../../contract/fixtures/plant_list.json";
import runsJson from "../../../contract/fixtures/run_list.json";
import startJson from "../../../contract/fixtures/start_run_result.json";
import { ApiClient } from "../api/client";
import type { Budget, PlantList, RunList } from "../api/schema";
import { AppProvider } from "../app/context";
import { buildHash } from "../app/router";
import { fakeFetch } from "../test/fakeFetch";
import { fixture } from "../test/fixtures";
import { RunStart } from "./RunStart";

const budget = fixture<Budget>(budgetJson);
const plants = fixture<PlantList>(plantsJson);
const runs = fixture<RunList>(runsJson);
const LIVE: Budget = { ...budget, live_run_available: true, message: null };

async function mount(b: Budget = LIVE) {
  const fake = fakeFetch({
    "/runs": { body: runs },
    "/budget": { body: b },
    "/plants": { body: plants },
    "POST /runs": { body: startJson },
  });
  render(
    <AppProvider client={new ApiClient("", fake.impl)}>
      <RunStart />
    </AppProvider>,
  );
  await screen.findByRole("form", { name: "Start a run" });
  return fake;
}

const form = () => screen.getByRole("form", { name: "Start a run" });
const field = (name: string) =>
  within(form()).getByLabelText(name) as HTMLInputElement;
const startButton = () =>
  within(form()).getByRole("button", { name: "Start run" });
const refusals = () =>
  within(form())
    .queryAllByRole("listitem")
    .map((li) => li.textContent);

describe("the runs list", () => {
  it("opens each run's replay, shortlist and coverage", async () => {
    await mount();
    const hrefs = (name: string) =>
      screen.getAllByRole("link", { name }).map((a) => a.getAttribute("href"));
    expect(hrefs("Replay")).toEqual(
      runs.runs.map((r) => buildHash({ name: "live", runId: r.id })),
    );
    expect(hrefs("Shortlist")).toEqual(
      runs.runs.map((r) => buildHash({ name: "shortlist", runId: r.id })),
    );
    expect(hrefs("Coverage")).toEqual(
      runs.runs.map((r) => buildHash({ name: "coverage", runId: r.id })),
    );
  });
});

describe("the start form (C6, C7, C13, G5–G7)", () => {
  it("lists the uses offered to API runs, with the use's and the phase's remaining amounts", async () => {
    await mount();
    const uses = Array.from(
      (field("Use") as unknown as HTMLSelectElement).options,
    ).map((o) => o.value);
    expect(uses).toEqual(budget.api_run_uses);
    expect(form().textContent).toContain(
      "development: $5.00 left. Phase 5: $0.50 left of $0.50 (up to $0.50 this phase).",
    );
  });

  it("never pre-fills the spend cap or the post cap, and refuses until both are in", async () => {
    await mount();
    expect(field("Spend cap (USD)").value).toBe("");
    expect(field("Post cap (USD)").value).toBe("");
    expect(startButton()).toHaveProperty("disabled", true);
    expect(refusals()).toEqual(["Enter a spend cap.", "Enter a post cap."]);
  });

  it("shows spend cap + post cap as the maximum", async () => {
    await mount();
    fireEvent.change(field("Spend cap (USD)"), { target: { value: "0.2" } });
    fireEvent.change(field("Post cap (USD)"), { target: { value: "0.1" } });
    expect(form().textContent).toContain(
      "Up to $0.30: spend cap $0.20 + post cap $0.10",
    );
    expect(refusals()).toEqual([]);
    expect(startButton()).toHaveProperty("disabled", false);
  });

  it("refuses a maximum over the phase's remaining amount, with the reason", async () => {
    await mount();
    fireEvent.change(field("Spend cap (USD)"), { target: { value: "0.4" } });
    fireEvent.change(field("Post cap (USD)"), { target: { value: "0.2" } });
    expect(refusals()).toEqual([
      "Up to $0.60 is more than phase 5 has left ($0.50).",
    ]);
    expect(startButton()).toHaveProperty("disabled", true);
  });

  it("asks to confirm in the page, then sends the use and both caps", async () => {
    const fake = await mount();
    fireEvent.change(field("Use") as unknown as HTMLSelectElement, {
      target: { value: "video" },
    });
    fireEvent.change(field("Spend cap (USD)"), { target: { value: "0.2" } });
    fireEvent.change(field("Post cap (USD)"), { target: { value: "0.1" } });
    fireEvent.click(startButton());
    expect(fake.calls.some((c) => c.method === "POST")).toBe(false);
    expect(form().textContent).toContain(
      "Start a full run that can spend up to $0.30?",
    );
    fireEvent.click(within(form()).getByRole("button", { name: "Confirm" }));
    const sent = await screen.findByRole("status");
    expect(fake.calls.find((c) => c.method === "POST")).toEqual({
      method: "POST",
      path: "/runs",
      body: {
        plant_id: plants.plants[0]?.plant_record_id,
        spend_cap_usd: 0.2,
        post_spend_cap_usd: 0.1,
        mode: "full",
        use: "video",
      },
    });
    expect(sent.textContent).toContain("Run started: estimated cost $0.20.");
    expect(
      within(sent)
        .getByRole("link", { name: "Watch it live" })
        .getAttribute("href"),
    ).toBe(buildHash({ name: "live", runId: startJson.run_id }));
  });

  it("is refused with the server's reason where live runs are off", async () => {
    await mount(budget);
    fireEvent.change(field("Spend cap (USD)"), { target: { value: "0.1" } });
    fireEvent.change(field("Post cap (USD)"), { target: { value: "0.1" } });
    expect(refusals()).toEqual(["Mock mode: no live runs."]);
    expect(startButton()).toHaveProperty("disabled", true);
  });
});
