import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ApiClient } from "../api/client";
import { fakeFetch } from "../test/fakeFetch";
import { AppProvider } from "./context";
import { buildHash, type Route } from "./router";
import { Screen } from "./Screen";

const RUN = "run:eaf6f55e4d2a4a30";
const enc = encodeURIComponent;

function show(route: Route) {
  render(
    <AppProvider client={new ApiClient("", fakeFetch({}).impl)}>
      <Screen route={route} />
    </AppProvider>,
  );
}

describe("routes with no screen yet (Bhargavi, 2026-10-27)", () => {
  it("the worksheet offers both downloads and says where the worksheet is", () => {
    show({ name: "worksheet", runId: RUN });
    const links = within(screen.getByRole("list", { name: "Export" }))
      .getAllByRole("link")
      .map((a) => [a.textContent, a.getAttribute("href")]);
    expect(links).toEqual([
      ["Worksheet (.xlsx)", `/runs/${enc(RUN)}/export.xlsx`],
      ["Run record (.json)", `/runs/${enc(RUN)}/export/run.json`],
    ]);
    expect(
      screen.getByText(
        "The full worksheet is in the Excel file; an on-screen worksheet is next.",
      ),
    ).toBeTruthy();
  });

  it.each<Route>([
    { name: "plants" },
    { name: "plant", plantId: "plant:mock_plant_a:be40872ede387491" },
    { name: "sections", plantId: "plant:mock_plant_a:be40872ede387491" },
  ])("$name says what is next and links to the runs", (route) => {
    show(route);
    expect(screen.getByText(/Plant input and sections are next/)).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "runs list" }).getAttribute("href"),
    ).toBe(buildHash({ name: "runs" }));
  });

  it.each<Route>([
    { name: "worksheet", runId: RUN },
    { name: "plants" },
    { name: "plant", plantId: "p" },
    { name: "sections", plantId: "p" },
  ])("$name shows no placeholder", (route) => {
    show(route);
    expect(document.querySelector(".placeholder")).toBeNull();
    expect(document.body.textContent).not.toMatch(/arrives with/);
  });
});
