import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import budget from "../../contract/fixtures/budget.json";
import plantList from "../../contract/fixtures/plant_list.json";
import runDetail from "../../contract/fixtures/run_detail.json";
import runList from "../../contract/fixtures/run_list.json";
import App from "./App";
import { ApiClient } from "./api/client";
import type { RunDetail } from "./api/schema";
import { buildHash } from "./app/router";
import { fakeFetch } from "./test/fakeFetch";
import { fixture } from "./test/fixtures";

const RUN = fixture<RunDetail>(runDetail).run.id;

function client(): ApiClient {
  const fake = fakeFetch({
    "/plants": { body: plantList },
    "/runs": { body: runList },
    [`/runs/${encodeURIComponent(RUN)}`]: { body: runDetail },
    "/budget": { body: budget },
  });
  return new ApiClient("", fake.impl);
}

afterEach(() => {
  window.location.hash = "";
});

describe("App", () => {
  it("renders the shell around the screen the hash names, with no console error", async () => {
    const errors = vi.spyOn(console, "error");
    window.location.hash = buildHash({ name: "shortlist", runId: RUN });
    render(<App client={client()} />);
    expect(screen.getByRole("heading", { name: "Guideword" })).toBeDefined();
    expect(
      await screen.findByRole("heading", { name: "Shortlist" }),
    ).toBeDefined();
    expect(await screen.findByRole("status")).toBeDefined();
    expect(errors).not.toHaveBeenCalled();
  });

  it("follows the hash", async () => {
    render(<App client={client()} />);
    expect(
      await screen.findByRole("heading", { name: "Plants" }),
    ).toBeDefined();
    act(() => {
      window.location.hash = buildHash({ name: "coverage", runId: RUN });
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    expect(
      await screen.findByRole("heading", { name: "Coverage" }),
    ).toBeDefined();
  });

  it("names a path it does not know", async () => {
    window.location.hash = "#/nowhere";
    render(<App client={client()} />);
    expect(
      await screen.findByRole("heading", { name: "Not found" }),
    ).toBeDefined();
    expect(screen.getByText("/nowhere", { exact: false })).toBeDefined();
  });
});
