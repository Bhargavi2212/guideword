import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import shortlistJson from "../../../contract/fixtures/shortlist.json";
import { ApiClient } from "../api/client";
import type { Shortlist as ShortlistData } from "../api/schema";
import { AppProvider } from "../app/context";
import { buildHash } from "../app/router";
import { fakeFetch } from "../test/fakeFetch";
import { fixture } from "../test/fixtures";
import { isSkipped, shownFlag, skippedLine } from "../model/evidence";
import { keyName } from "../model/names";
import { gapWords, lopaLine, severityText } from "../model/technical";
import { lineTitle } from "../model/titles";
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

  it("offers the worksheet and the run record for download", async () => {
    await shortlist();
    expect(
      within(screen.getByRole("list", { name: "Export" }))
        .getAllByRole("link")
        .map((a) => a.getAttribute("href")),
    ).toEqual([
      `/runs/${encodeURIComponent(RUN)}/export.xlsx`,
      `/runs/${encodeURIComponent(RUN)}/export/run.json`,
    ]);
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

  it("shows every flag verbatim on its card, the evidence-skipped flag as its count", async () => {
    await shortlist();
    for (const item of data.items) {
      const flags = within(card(item.target_id))
        .queryAllByRole("listitem")
        .filter((li) => li.closest(".flags") !== null)
        .map((li) => li.textContent);
      expect(flags).toEqual((item.flags ?? []).map(shownFlag));
      for (const flag of item.flags ?? [])
        if (!flag.startsWith("evidence skipped")) expect(flags).toContain(flag);
    }
  });

  it("shows the gap as N times over the risk limit, and no LOPA as no LOPA (Q10)", async () => {
    await shortlist();
    for (const item of data.items) {
      const text = card(item.target_id).textContent ?? "";
      expect(text).toContain(gapWords(item));
    }
    const pair = must(
      data.items.find((i) => i.target_id.startsWith("f:pair:")),
    );
    expect(card(pair.target_id).textContent).toContain(
      "1,000× over the risk limit",
    );
  });

  it("puts a plain title on top and the technical layer below it (R3)", async () => {
    await shortlist();
    for (const item of data.items) {
      const el = card(item.target_id);
      expect(el.querySelector(".card-title")?.textContent).toBe(
        lineTitle(item),
      );
      if (item.lopa)
        expect(el.querySelector(".card-lopa")?.textContent).toBe(
          lopaLine(item.lopa),
        );
      const severity =
        item.chain?.severity_class ?? item.finding?.severity_class;
      if (severity)
        expect(el.querySelector(".card-severity")?.textContent).toBe(
          severityText(severity, data.severity_classes),
        );
    }
  });

  it("shows no raw record key in a card's title or lead text (Q7)", async () => {
    await shortlist();
    for (const item of data.items) {
      const el = card(item.target_id);
      for (const part of [".card-title", ".card-lead"]) {
        expect(el.querySelector(part)?.textContent ?? "").not.toMatch(
          /\b(?:f|m|ch|proc|pair|env|hyp):\S/,
        );
      }
    }
  });

  it("says what each calculation card is on and what it is attached through", async () => {
    await shortlist();
    const chain = must(data.items.find((i) => i.target_kind === "chain"));
    const calc = must(
      (chain.evidence ?? []).find((e) => e.kind === "calculation"),
    );
    const text = card(chain.target_id).textContent ?? "";
    expect(text).toContain("calculation on MX-1 · via ");
    for (const via of calc.via_ids ?? []) expect(text).toContain(keyName(via));
  });

  it("shows up to three evidence chips with their summaries", async () => {
    await shortlist();
    for (const item of data.items) {
      const chips = card(item.target_id).querySelectorAll(".chip-verdict");
      const evidence = (item.evidence ?? []).slice(0, 3);
      expect(chips.length).toBe(evidence.length);
      for (const e of evidence.filter((x) => !isSkipped(x)))
        expect(card(item.target_id).textContent).toContain(e.summary);
    }
  });

  it("shows a skipped calculation as one line, not its list of facts", async () => {
    await shortlist();
    const lines = data.items.filter((i) =>
      (i.evidence ?? []).slice(0, 3).some(isSkipped),
    );
    expect(lines.length).toBeGreaterThan(0);
    for (const item of lines) {
      const text = card(item.target_id).textContent;
      for (const e of (item.evidence ?? []).slice(0, 3).filter(isSkipped)) {
        expect(text).toContain(skippedLine(e));
        expect(text).not.toContain(e.summary);
      }
    }
  });

  it("gives the evidence-skipped flag as a count, with the facts left to the card", async () => {
    await shortlist();
    const flagged = must(
      data.items.find((i) =>
        (i.flags ?? []).some((f) => f.startsWith("evidence skipped")),
      ),
    );
    const flags = within(card(flagged.target_id)).getAllByRole("listitem");
    const skip = must(
      flags.find((f) => f.textContent.startsWith("evidence skipped")),
    );
    expect(skip.textContent).toMatch(
      /^evidence skipped: \d+ plant facts? missing$/,
    );
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

describe("the demo moment's card (deploy plan D3)", () => {
  async function withDemo(startTargetId: string | null, banner?: string) {
    const demo = await import("../../../contract/fixtures/demo_response.json");
    // contract v1.11: each run's own entry names its start line
    const runs = demo.default.runs.map((r) =>
      r.run_id === RUN
        ? { ...r, start_target_id: startTargetId, banner: banner ?? r.banner }
        : r,
    );
    const label = { ...data.label, kind: "recorded" };
    const fake = fakeFetch({
      [`/runs/${encodeURIComponent(RUN)}/shortlist`]: {
        body: { ...data, label },
      },
      "/demo": {
        body: { ...demo.default, start_target_id: startTargetId, runs },
      },
    });
    render(
      <AppProvider client={new ApiClient("", fake.impl)}>
        <Shortlist runId={RUN} />
      </AppProvider>,
    );
    await screen.findAllByRole("article");
  }

  it("is marked start here, and no other card is", async () => {
    const chain = must(data.items.find((i) => i.target_kind === "chain"));
    await withDemo(chain.target_id);
    expect(
      await within(card(chain.target_id)).findByText("start here"),
    ).toBeDefined();
    expect(screen.getAllByText("start here")).toHaveLength(1);
  });

  it("opens at the top: no card is scrolled into view (F6)", async () => {
    const scrolled: Element[] = [];
    const spy = vi
      .spyOn(Element.prototype, "scrollIntoView")
      .mockImplementation(function (this: Element) {
        scrolled.push(this);
      });
    const chain = must(data.items.find((i) => i.target_kind === "chain"));
    await withDemo(chain.target_id);
    await within(card(chain.target_id)).findByText("start here");
    expect(scrolled).toEqual([]);
    spy.mockRestore();
  });

  it("makes the banner's 'Line #N' a link that scrolls to the start card (F6)", async () => {
    const scrolled: Element[] = [];
    const spy = vi
      .spyOn(Element.prototype, "scrollIntoView")
      .mockImplementation(function (this: Element) {
        scrolled.push(this);
      });
    const chain = must(data.items.find((i) => i.target_kind === "chain"));
    const banner = `Rebuilt from a report. Line #${String(chain.rank)} is the accident.`;
    await withDemo(chain.target_id, banner);
    const note = await screen.findByRole("note");
    expect(note.textContent).toBe(banner);
    fireEvent.click(
      within(note).getByRole("button", { name: `Line #${String(chain.rank)}` }),
    );
    expect(scrolled).toEqual([card(chain.target_id)]);
    spy.mockRestore();
  });

  it("leaves the banner plain when its line number is not the start card's", async () => {
    const chain = must(data.items.find((i) => i.target_kind === "chain"));
    const banner = `Line #${String(chain.rank + 1)} is something else.`;
    await withDemo(chain.target_id, banner);
    const note = await screen.findByRole("note");
    expect(note.textContent).toBe(banner);
    expect(within(note).queryByRole("button")).toBeNull();
  });

  it("is not marked when the demo names none", async () => {
    await withDemo(null);
    expect(screen.queryByText("start here")).toBeNull();
  });
});

describe("the site's runs: banner and plant picker (review plan R3)", () => {
  const OTHER = "run:0123456789abcdef";
  const BANNER =
    "Rebuilt from a public report. Line #2 is the accident Guideword found.";

  async function site(kind: "recorded" | "mock", runId: string = RUN) {
    const demo = await import("../../../contract/fixtures/demo_response.json");
    const runs = [
      {
        run_id: RUN,
        plant_id: "williams_geismar",
        banner: BANNER,
        start_target_id: null,
      },
      {
        run_id: OTHER,
        plant_id: "case_d",
        banner: "Unit D: a development case.",
        start_target_id: null,
      },
    ];
    const label = { ...data.label, kind };
    const fake = fakeFetch({
      [`/runs/${encodeURIComponent(runId)}/shortlist`]: {
        body: { ...data, run_id: runId, label },
      },
      "/demo": { body: { ...demo.default, runs } },
    });
    render(
      <AppProvider client={new ApiClient("", fake.impl)}>
        <Shortlist runId={runId} />
      </AppProvider>,
    );
    await screen.findAllByRole("article");
  }

  afterEach(() => {
    window.location.hash = "";
  });

  it("shows the run's own banner on a recorded run", async () => {
    await site("recorded");
    expect((await screen.findByRole("note")).textContent).toBe(BANNER);
  });

  it("shows no banner on a run that isn't recorded", async () => {
    await site("mock");
    await screen.findByLabelText("Plant");
    expect(screen.queryByRole("note")).toBeNull();
  });

  it("shows D's banner on D, with none of WG's words", async () => {
    await site("recorded", OTHER);
    const note = await screen.findByRole("note");
    expect(note.textContent).toBe("Unit D: a development case.");
    expect(note.textContent).not.toContain("found");
  });

  it("offers the site's runs in the server's order, WG first, and opens the one chosen", async () => {
    await site("recorded");
    const picker = (await screen.findByLabelText("Plant")) as HTMLSelectElement;
    expect(Array.from(picker.options).map((o) => o.textContent)).toEqual([
      "williams_geismar",
      "case_d",
    ]);
    expect(picker.value).toBe(RUN);
    fireEvent.change(picker, { target: { value: OTHER } });
    expect(window.location.hash).toBe(
      buildHash({ name: "shortlist", runId: OTHER }),
    );
  });

  it("marks no line 'start here' on a run whose entry names none", async () => {
    await site("recorded", OTHER);
    expect(screen.queryByText("start here")).toBeNull();
  });
});

describe("a chain with the chain-finder's own handles (D and G, decisions row 251)", () => {
  it("is flagged with its numbers, in Bhargavi's words", async () => {
    const chain = must(data.items.find((i) => i.target_kind === "chain"));
    const flagged = {
      ...chain,
      chain: { ...must(chain.chain), description: "L9 heats P51 through L34" },
    };
    const items = data.items.map((i) =>
      i.target_id === chain.target_id ? flagged : i,
    );
    await shortlist({ ...data, items });
    expect(card(chain.target_id).textContent).toContain(
      "Line and step numbers (L9, P51, L34) from the chain-finder’s prompt; not resolved to plant tags in this development run.",
    );
  });

  it("is not flagged when no handle is left", async () => {
    await shortlist();
    for (const item of data.items)
      expect(card(item.target_id).textContent).not.toContain("chain-finder");
  });
});
