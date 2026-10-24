import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import plantDetail from "../../../contract/fixtures/plant_detail.json";
import recordDetail from "../../../contract/fixtures/record_detail.json";
import { ApiClient } from "../api/client";
import type { PlantDetail, RecordDetail } from "../api/schema";
import { AppProvider } from "../app/context";
import { fakeFetch } from "../test/fakeFetch";
import { fixture } from "../test/fixtures";
import { must } from "../test/must";
import { RecordDrawer } from "./RecordDrawer";

const record = fixture<RecordDetail>(recordDetail);
const plant = fixture<PlantDetail>(plantDetail);
const RUN = record.run_id;
const PLANT = plant.plant_record_id;
const enc = encodeURIComponent;

function drawer(recordId: string, routes = {}) {
  const fake = fakeFetch({
    [`/runs/${enc(RUN)}/records/${enc(record.record_id)}`]: { body: record },
    [`/plants/${enc(PLANT)}`]: { body: plant },
    ...routes,
  });
  render(
    <AppProvider client={new ApiClient("", fake.impl)}>
      <RecordDrawer
        runId={RUN}
        plantId={PLANT}
        recordId={recordId}
        onClose={() => {}}
      />
    </AppProvider>,
  );
  return fake;
}

describe("RecordDrawer", () => {
  it("shows a record with its parents and the calls that made it", async () => {
    drawer(record.record_id);
    const panel = await screen.findByRole("dialog", { name: /finding/i });
    expect(within(panel).getByText(record.record_id)).toBeDefined();
    for (const parent of record.parent_ids) {
      expect(within(panel).getByRole("button", { name: parent })).toBeDefined();
    }
    const [call] = record.model_calls;
    expect(call).toBeDefined();
    expect(
      within(panel).getByText(must(call).model_id, { exact: false }),
    ).toBeDefined();
  });

  it("shows a plant fact with its value and source", async () => {
    const fact = must(plant.facts.find((f) => f.source === "SDS"));
    drawer(fact.id);
    const panel = await screen.findByRole("dialog", { name: /plant fact/i });
    expect(
      within(panel).getByText(String(fact.value), { exact: false }),
    ).toBeDefined();
    expect(within(panel).getByText("SDS")).toBeDefined();
  });

  it("highlights an assumed fact", async () => {
    const fact = must(plant.facts.find((f) => f.source === "assumed"));
    drawer(fact.id);
    const panel = await screen.findByRole("dialog", { name: /plant fact/i });
    expect(within(panel).getByText("assumed").className).toContain("assumed");
  });

  it("reads a fact the plant file does not state as not stated (C11)", async () => {
    drawer("EA-425B.heat_duty_kw");
    const panel = await screen.findByRole("dialog", { name: /plant fact/i });
    expect(
      within(panel).getByText("not stated in the plant file"),
    ).toBeDefined();
  });

  it("reads a record the API does not know as not addressable yet", async () => {
    drawer("tc:step:unknown:physics_calc:0000000000000000");
    const panel = await screen.findByRole("dialog");
    expect(await within(panel).findByText("not addressable yet")).toBeDefined();
  });
});
