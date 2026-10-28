import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import budget from "../../../contract/fixtures/budget.json";
import plantList from "../../../contract/fixtures/plant_list.json";
import runDetail from "../../../contract/fixtures/run_detail.json";
import runList from "../../../contract/fixtures/run_list.json";
import { ApiClient } from "../api/client";
import type { Budget, PlantList, RunDetail, RunList } from "../api/schema";
import { fakeFetch } from "../test/fakeFetch";
import { fixture } from "../test/fixtures";
import { must } from "../test/must";
import { AppProvider } from "./context";
import { ENGINEER_KEY, loadEngineer, saveEngineer } from "./engineer";
import { buildHash } from "./router";
import { Shell } from "./Shell";

const plants = fixture<PlantList>(plantList);
const runs = fixture<RunList>(runList);
const detail = fixture<RunDetail>(runDetail);
const RUN = detail.run.id;

function shell(route = { name: "shortlist" as const, runId: RUN }) {
  const fake = fakeFetch({
    "/plants": { body: plants },
    "/runs": { body: runs },
    [`/runs/${encodeURIComponent(RUN)}`]: { body: detail },
    "/budget": { body: fixture<Budget>(budget) },
  });
  render(
    <AppProvider client={new ApiClient("", fake.impl)}>
      <Shell route={route}>
        <p>screen</p>
      </Shell>
    </AppProvider>,
  );
  return fake;
}

afterEach(() => {
  window.localStorage.clear();
  window.location.hash = "";
});

describe("Shell header", () => {
  it("renders from the fixtures with no console error", async () => {
    const errors = vi.spyOn(console, "error");
    shell();
    expect(await screen.findByRole("status")).toBeDefined();
    expect(errors).not.toHaveBeenCalled();
  });

  it("lists the plants and the runs, and a choice changes the route", async () => {
    shell();
    const runSelect = await screen.findByLabelText("Run");
    const options = Array.from((runSelect as HTMLSelectElement).options).map(
      (o) => o.value,
    );
    for (const run of runs.runs) expect(options).toContain(run.id);
    const other = must(runs.runs[1]).id;
    fireEvent.change(runSelect, { target: { value: other } });
    expect(window.location.hash).toBe(
      buildHash({ name: "shortlist", runId: other }),
    );
    // plant input is not on the site yet, so a plant opens its first run's shortlist
    const plant = must(plants.plants[0]).plant_record_id;
    const first = must(runs.runs.find((r) => r.plant_record_id === plant));
    const plantSelect = await screen.findByLabelText("Plant");
    fireEvent.change(plantSelect, { target: { value: plant } });
    expect(window.location.hash).toBe(
      buildHash({ name: "shortlist", runId: first.id }),
    );
  });

  it("links the brand to the runs list, never to a screen not yet built", () => {
    shell();
    expect(
      screen.getByRole("link", { name: "Guideword" }).getAttribute("href"),
    ).toBe(buildHash({ name: "runs" }));
  });

  it("shows the run's label, status, step and its spend against its cap, traced", async () => {
    shell();
    expect((await screen.findByRole("status")).textContent).toBe(
      "Mock data — not a real plant",
    );
    expect(
      await screen.findByText(`${detail.run.status} · ${detail.run.step}`),
    ).toBeDefined();
    const spend = await screen.findByRole("button", {
      name: /spent .* of .*cap/i,
    });
    expect(spend.getAttribute("data-record-id")).toBe(RUN);
  });

  it("shows the API runs' budget: each offered use and the phase's remaining cap", async () => {
    shell();
    const lines = await screen.findByLabelText("Budget");
    expect(lines.textContent).toContain("development $5.00 left");
    expect(lines.textContent).toContain("video $2.00 left");
    expect(lines.textContent).toContain("phase 5 $0.50 left");
  });
});

describe("engineer name (P5-7)", () => {
  it("survives a reload", async () => {
    shell();
    const input = await screen.findByLabelText("Engineer");
    fireEvent.change(input, { target: { value: "B. Nallapuneni" } });
    expect(window.localStorage.getItem(ENGINEER_KEY)).toBe("B. Nallapuneni");
    expect(loadEngineer(window.localStorage)).toBe("B. Nallapuneni");
  });

  it("is kept for the session when storage fails", () => {
    const broken = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
    } as unknown as Storage;
    expect(loadEngineer(broken)).toBe("");
    expect(() => act(() => saveEngineer(broken, "B"))).not.toThrow();
  });
});

describe("the spend note (deploy plan §0.3)", () => {
  it("shows the label's note beside the run's spend, traced to the run", async () => {
    const note =
      "record $0.0083 under ledger: run recorded on code before the refused-retry fix (#103)";
    const noted = {
      ...detail,
      label: { ...detail.label, kind: "recorded", note },
    };
    const fake = fakeFetch({
      "/plants": { body: plants },
      "/runs": { body: runs },
      [`/runs/${encodeURIComponent(RUN)}`]: { body: noted },
      "/budget": { body: fixture<Budget>(budget) },
    });
    render(
      <AppProvider client={new ApiClient("", fake.impl)}>
        <Shell route={{ name: "shortlist", runId: RUN }}>
          <p>screen</p>
        </Shell>
      </AppProvider>,
    );
    const shown = await screen.findByText(note);
    expect(
      shown.closest("[data-record-id]")?.getAttribute("data-record-id"),
    ).toBe(RUN);
  });
});

describe("a recorded run (Bhargavi's review, 2026-10-25)", () => {
  function recorded() {
    const shown = { ...detail, label: { ...detail.label, kind: "recorded" } };
    const fake = fakeFetch({
      "/plants": { body: plants },
      "/runs": { body: runs },
      [`/runs/${encodeURIComponent(RUN)}`]: { body: shown },
      "/budget": { body: fixture<Budget>(budget) },
    });
    render(
      <AppProvider client={new ApiClient("", fake.impl)}>
        <Shell route={{ name: "shortlist", runId: RUN }}>
          <p>screen</p>
        </Shell>
      </AppProvider>,
    );
  }

  it("hides the phase budget, the engineer's name and the plant status", async () => {
    recorded();
    await screen.findByRole("status");
    const plantSelect = await screen.findByLabelText("Plant");
    await within(plantSelect).findByText(must(plants.plants[0]).plant_id);
    expect(screen.queryByLabelText("Budget")).toBeNull();
    expect(screen.queryByLabelText("Engineer")).toBeNull();
    for (const p of plants.plants)
      expect(plantSelect.textContent).not.toContain(`(${p.status})`);
  });

  it("still shows them on a mock run", async () => {
    shell();
    await screen.findByLabelText("Budget");
    expect(screen.getByLabelText("Engineer")).toBeDefined();
    const first = must(plants.plants[0]);
    await within(screen.getByLabelText("Plant")).findByText(
      `${first.plant_id} (${first.status})`,
    );
  });
});
