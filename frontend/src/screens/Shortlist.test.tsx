import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import shortlistJson from "../../../contract/fixtures/shortlist.json";
import { ApiClient } from "../api/client";
import type { Shortlist as ShortlistData } from "../api/schema";
import { AppProvider } from "../app/context";
import { buildHash } from "../app/router";
import { fakeFetch } from "../test/fakeFetch";
import { fixture } from "../test/fixtures";
import { must } from "../test/must";
import { Shortlist } from "./Shortlist";

const data = fixture<ShortlistData>(shortlistJson);
const RUN = data.run_id;

async function shortlist(body: unknown = data) {
  const fake = fakeFetch({
    [`/runs/${encodeURIComponent(RUN)}/shortlist`]: { body },
  });
  render(
    <AppProvider client={new ApiClient("", fake.impl)}>
      <Shortlist runId={RUN} />
    </AppProvider>,
  );
  await screen.findAllByRole("article");
}

function card(targetId: string): HTMLElement {
  const found = screen
    .getAllByRole("article")
    .find((a) => a.getAttribute("data-target-id") === targetId);
  if (found === undefined) throw new Error(`no card for ${targetId}`);
  return found;
}

describe("Shortlist (spec 5.1)", () => {
  it("renders from its fixture with no console error", async () => {
    const errors = vi.spyOn(console, "error");
    await shortlist();
    expect(errors).not.toHaveBeenCalled();
  });

  it("shows the three tiers in order, each card where the server put it", async () => {
    await shortlist();
    const headings = screen
      .getAllByRole("heading", { level: 3 })
      .map((h) => h.textContent);
    expect(headings).toEqual(["Confirmed", "Also found", "Unconfirmed"]);
    const shown = screen
      .getAllByRole("article")
      .map((a) => a.getAttribute("data-target-id"));
    const served = ["confirmed", "also_found", "unconfirmed"].flatMap((tier) =>
      data.items.filter((i) => i.tier === tier).map((i) => i.target_id),
    );
    expect(shown).toEqual(served);
  });

  it("shows every flag verbatim on its card", async () => {
    await shortlist();
    for (const item of data.items) {
      const flags = within(card(item.target_id))
        .queryAllByRole("listitem")
        .filter((li) => li.closest(".flags") !== null)
        .map((li) => li.textContent);
      expect(flags).toEqual(item.flags ?? []);
    }
  });

  it("shows the gap as the server wrote it, and no LOPA as no LOPA", async () => {
    await shortlist();
    for (const item of data.items) {
      const text = card(item.target_id).textContent ?? "";
      if (item.gap_text) expect(text).toContain(item.gap_text);
      else expect(text).toContain("no LOPA");
    }
  });

  it("shows up to three evidence chips with their summaries", async () => {
    await shortlist();
    for (const item of data.items) {
      const chips = card(item.target_id).querySelectorAll(".chip-verdict");
      const evidence = (item.evidence ?? []).slice(0, 3);
      expect(chips.length).toBe(evidence.length);
      for (const e of evidence)
        expect(card(item.target_id).textContent).toContain(e.summary);
    }
  });

  it("names the hypothesis rank on a confirmed card and flags an unconfirmed one", async () => {
    await shortlist();
    const confirmed = must(
      data.items.find((i) => i.tier === "confirmed" && i.hypothesis_rank),
    );
    expect(card(confirmed.target_id).textContent).toContain(
      `hypothesis ${confirmed.hypothesis_rank}`,
    );
    const unconfirmed = must(data.items.find((i) => i.tier === "unconfirmed"));
    expect(card(unconfirmed.target_id).textContent).toContain(
      "not confirmed by the checks — engineer to review",
    );
  });

  it("opens each card's finding detail", async () => {
    await shortlist();
    for (const item of data.items) {
      const link = within(card(item.target_id)).getByRole("link");
      expect(link.getAttribute("href")).toBe(
        buildHash({ name: "item", runId: RUN, targetId: item.target_id }),
      );
    }
  });

  it("moves between cards with the arrow keys", async () => {
    await shortlist();
    const links = screen
      .getAllByRole("article")
      .map((a) => within(a).getByRole("link"));
    links[0]?.focus();
    fireEvent.keyDown(links[0] as HTMLElement, { key: "ArrowDown" });
    expect(document.activeElement).toBe(links[1]);
    fireEvent.keyDown(links[1] as HTMLElement, { key: "ArrowUp" });
    expect(document.activeElement).toBe(links[0]);
  });

  it("puts every number on a card inside a traced value (P5-6)", async () => {
    await shortlist();
    const untraced: string[] = [];
    for (const article of screen.getAllByRole("article")) {
      const walker = document.createTreeWalker(article, NodeFilter.SHOW_TEXT);
      for (
        let node = walker.nextNode();
        node !== null;
        node = walker.nextNode()
      ) {
        const text = node.textContent ?? "";
        if (
          /\d/.test(text) &&
          node.parentElement?.closest(".traced") === null
        ) {
          untraced.push(text);
        }
      }
    }
    expect(untraced).toEqual([]);
  });
});
