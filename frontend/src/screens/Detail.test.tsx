import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import shortlistJson from "../../../contract/fixtures/shortlist.json";
import { ApiClient } from "../api/client";
import type { Shortlist, ShortlistItem } from "../api/schema";
import { AppProvider } from "../app/context";
import { Shell } from "../app/Shell";
import { fakeFetch, type FakeResponse } from "../test/fakeFetch";
import { fixture } from "../test/fixtures";
import demoJson from "../test/fixtures/wg_demo_item.json";
import { calculationOf, isSkipped, skippedLine } from "../model/evidence";
import { nameKeys, undoNames } from "../model/names";
import { findingQuestion, questionTitle } from "../model/titles";
import { must } from "../test/must";
import { Detail } from "./Detail";

const mock = fixture<Shortlist>(shortlistJson);
const MOCK_RUN = mock.run_id;
const enc = encodeURIComponent;
const LIVE = { kind: "live" as const, recorded_at: null, cost_usd: null };

type Demo = {
  run_detail: { run: { id: string; plant_record_id: string }; label: unknown };
  item: ShortlistItem;
  plant_detail: { plant_record_id: string };
};
const demo = demoJson as unknown as Demo;
const DEMO_RUN = demo.run_detail.run.id;

function item(prefix: string): ShortlistItem {
  return must(
    mock.items.find((i) => i.target_id.startsWith(prefix)),
    prefix,
  );
}

/** The shortlist served live, so overrides may be sent (the generated one is mock). */
function live(list: Shortlist): Shortlist {
  return { ...list, label: LIVE };
}

function detail(
  runId: string,
  targetId: string,
  routes: Record<string, FakeResponse | (() => FakeResponse)>,
) {
  const fake = fakeFetch(routes);
  render(
    <AppProvider client={new ApiClient("", fake.impl)}>
      <Detail runId={runId} targetId={targetId} />
    </AppProvider>,
  );
  return fake;
}

function mockDetail(prefix: string, list: Shortlist = mock) {
  const target = item(prefix).target_id;
  return detail(MOCK_RUN, target, {
    [`/runs/${enc(MOCK_RUN)}/shortlist`]: { body: list },
    [`POST /runs/${enc(MOCK_RUN)}/overrides`]: {
      body: { override: {}, stored: true },
    },
  });
}

afterEach(() => {
  window.localStorage.clear();
});

describe("Detail (spec 5.2)", () => {
  it("renders from its fixtures with no console error", async () => {
    const errors = vi.spyOn(console, "error");
    mockDetail("ch:");
    await screen.findByRole("heading", { level: 2 });
    expect(errors).not.toHaveBeenCalled();
  });

  it("lists a chain's links in order, each finding and fact traced", async () => {
    const chain = must(item("ch:").chain);
    mockDetail("ch:");
    const links = await screen.findByRole("list", { name: "Links" });
    // each box's first traced span is its link (a calculation in a box is traced to itself)
    const traced = Array.from(links.querySelectorAll(":scope > li")).map((li) =>
      li.querySelector("[data-record-id]")?.getAttribute("data-record-id"),
    );
    expect(traced).toEqual(chain.links);
  });

  it("keeps Ultra's argument apart from code's credit and reason, a refused layer styled", async () => {
    const lopa = must(item("f:m:S-MX-1:more:temperature:").lopa);
    mockDetail("f:m:S-MX-1:more:temperature:");
    const table = await screen.findByRole("table", {
      name: "Protection layers",
    });
    for (const layer of lopa.layers ?? []) {
      const row = must(
        within(table)
          .getAllByRole("row")
          .find((r) => r.getAttribute("data-layer-id") === layer.layer_id),
      );
      const ultra = must(row.querySelector("[data-column='ultra']"));
      const code = must(row.querySelector("[data-column='code']"));
      expect(code.textContent).toContain(layer.reason);
      if (layer.argument) expect(ultra.textContent).toContain(layer.argument);
      expect(ultra.textContent).not.toContain(layer.reason);
      expect(row.classList.contains("refused")).toBe(!layer.credited);
    }
  });

  it("lists an incomplete LOPA's missing facts, traced", async () => {
    const lopa = must(item("f:m:S-L-12:reverse:flow:").lopa);
    mockDetail("f:m:S-L-12:reverse:flow:");
    const missing = await screen.findByRole("list", { name: "Missing facts" });
    expect(
      within(missing)
        .getAllByRole("button")
        .map((b) => b.getAttribute("data-record-id")),
    ).toEqual(lopa.missing_fact_ids);
  });

  it("names the equipment each calculation card is on", async () => {
    const mx1 = item("f:m:S-MX-1:more:temperature:");
    mockDetail("f:m:S-MX-1:more:temperature:");
    const cards = await screen.findAllByRole("article");
    const calcs = (mx1.evidence ?? []).filter((e) => e.kind === "calculation");
    expect(calcs.length).toBeGreaterThan(0);
    for (const e of calcs) {
      const card = must(
        cards.find((c) => c.getAttribute("data-evidence-id") === e.id),
      );
      expect(card.querySelector(".kind")?.textContent).toBe(
        `calculation on ${must(calculationOf(e)).equipment_id}`,
      );
    }
  });

  it("shows a skipped calculation as one line, its missing facts traced when opened", async () => {
    // the mock's skipped blocked-in check is on its chain, which names MX-1 and XV-STM
    const chain = item("ch:");
    mockDetail("ch:");
    const cards = await screen.findAllByRole("article");
    const skipped = (chain.evidence ?? []).filter(isSkipped);
    expect(skipped.length).toBeGreaterThan(0);
    for (const e of skipped) {
      const card = must(
        cards.find((c) => c.getAttribute("data-evidence-id") === e.id),
      );
      expect(card.querySelector("summary")?.textContent).toBe(skippedLine(e));
      expect(card.textContent).not.toContain(e.summary);
      const missing = within(card).getByRole("list", { name: "Missing facts" });
      expect(
        within(missing)
          .getAllByRole("button")
          .map((b) => b.getAttribute("data-record-id")),
      ).toEqual(e.missing_fact_ids);
    }
  });

  it("shows each evidence summary verbatim, its facts traced, its sources in a new tab", async () => {
    const mx1 = item("f:m:S-MX-1:more:temperature:");
    mockDetail("f:m:S-MX-1:more:temperature:");
    const cards = await screen.findAllByRole("article");
    for (const e of (mx1.evidence ?? []).filter((x) => !isSkipped(x))) {
      const card = must(
        cards.find((c) => c.getAttribute("data-evidence-id") === e.id),
      );
      expect(card.textContent).toContain(e.summary);
      const facts = Array.from(card.querySelectorAll("[data-record-id]")).map(
        (b) => b.getAttribute("data-record-id"),
      );
      for (const id of e.fact_ids ?? []) expect(facts).toContain(id);
      for (const source of e.sources ?? []) {
        const link = within(card).getByRole("link", { name: source });
        expect(link.getAttribute("target")).toBe("_blank");
        expect(link.getAttribute("rel")).toContain("noopener");
      }
    }
  });

  it("traces a confirmed line's supporting findings", async () => {
    const pair = item("f:pair:KOH:SIH:");
    mockDetail("f:pair:KOH:SIH:");
    if ((pair.support_finding_ids ?? []).length > 0) {
      const list = await screen.findByRole("list", {
        name: "Supporting findings",
      });
      expect(
        within(list)
          .getAllByRole("button")
          .map((b) => b.getAttribute("data-record-id")),
      ).toEqual(pair.support_finding_ids);
    }
  });

  it("titles each supporting finding, its raw key on hover (F6)", async () => {
    const pair = item("f:pair:KOH:SIH:");
    const ids = pair.support_finding_ids ?? [];
    expect(ids.length).toBeGreaterThan(0);
    mockDetail("f:pair:KOH:SIH:");
    const list = await screen.findByRole("list", {
      name: "Supporting findings",
    });
    const buttons = within(list).getAllByRole("button");
    expect(buttons.map((b) => b.textContent)).toEqual(
      ids.map((id) => questionTitle(findingQuestion(id))),
    );
    expect(buttons.map((b) => b.getAttribute("title"))).toEqual(ids);
    expect(buttons[0]?.textContent).toBe("KOH and SIH mix");
  });
});

describe("overrides (spec 5.2, P5-7)", () => {
  it("are disabled on a mock or recorded run, with the reason", async () => {
    mockDetail("ch:");
    expect(
      await screen.findByText("This is mock data: nothing is saved"),
    ).toBeDefined();
    for (const button of screen.getAllByRole("button", {
      name: /accept|reject|change severity/i,
    })) {
      expect((button as HTMLButtonElement).disabled).toBe(true);
    }
  });

  it("send change severity exactly, then reload the item", async () => {
    window.localStorage.setItem("guideword.engineer", "B. Engineer");
    const chain = item("ch:");
    let served = 0;
    const fake = detail(MOCK_RUN, chain.target_id, {
      [`/runs/${enc(MOCK_RUN)}/shortlist`]: () => {
        served += 1;
        return { body: live(mock) };
      },
      [`POST /runs/${enc(MOCK_RUN)}/overrides`]: {
        body: { override: {}, stored: true },
      },
    });
    await screen.findByRole("heading", { level: 2 });
    fireEvent.change(screen.getByLabelText("New severity"), {
      target: { value: "S4" },
    });
    fireEvent.change(screen.getByLabelText("Reason for the severity"), {
      target: { value: "Occupied on every shift." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Change severity" }));
    await vi.waitFor(() => expect(served).toBe(2));
    const posted = fake.calls.filter((c) => c.method === "POST");
    expect(posted.map((c) => c.body)).toEqual([
      {
        target_id: chain.target_id,
        action: "change_severity",
        new_value: { severity_class: "S4" },
        reason: "Occupied on every shift.",
        by: "B. Engineer",
      },
    ]);
  });

  it("need a reason and the engineer's name before they are sent", async () => {
    const fake = mockDetail("ch:", live(mock));
    await screen.findByRole("heading", { level: 2 });
    fireEvent.change(screen.getByLabelText("New severity"), {
      target: { value: "S4" },
    });
    const send = screen.getByRole("button", {
      name: "Change severity",
    }) as HTMLButtonElement;
    expect(send.disabled).toBe(true);
    expect(fake.calls.filter((c) => c.method === "POST")).toEqual([]);
  });

  it("accept, reject and edit a finding's consequence; accept and reject a chain", async () => {
    window.localStorage.setItem("guideword.engineer", "B");
    const finding = item("f:m:S-MX-1:more:temperature:");
    const fake = mockDetail("f:m:S-MX-1:more:temperature:", live(mock));
    await screen.findByRole("heading", { level: 2 });
    const panel = screen.getByRole("region", { name: "Overrides" });
    fireEvent.change(within(panel).getByLabelText("Reason"), {
      target: { value: "checked" },
    });
    fireEvent.click(
      within(panel).getByRole("button", { name: "Accept finding" }),
    );
    fireEvent.click(
      within(panel).getByRole("button", { name: "Reject finding" }),
    );
    fireEvent.change(within(panel).getByLabelText("Consequence"), {
      target: { value: "It overheats." },
    });
    fireEvent.click(
      within(panel).getByRole("button", { name: "Edit consequence" }),
    );
    await vi.waitFor(() =>
      expect(fake.calls.filter((c) => c.method === "POST").length).toBe(3),
    );
    const bodies = fake.calls
      .filter((c) => c.method === "POST")
      .map((c) => c.body);
    expect(bodies).toEqual([
      {
        target_id: finding.target_id,
        action: "accept",
        new_value: null,
        reason: "checked",
        by: "B",
      },
      {
        target_id: finding.target_id,
        action: "reject",
        new_value: null,
        reason: "checked",
        by: "B",
      },
      {
        target_id: finding.target_id,
        action: "edit",
        new_value: { consequence: "It overheats." },
        reason: "checked",
        by: "B",
      },
    ]);
  });

  it("accept, reject and edit a recommendation's action", async () => {
    window.localStorage.setItem("guideword.engineer", "B");
    const chain = item("ch:");
    const rec = must((chain.recommendations ?? [])[0]);
    const fake = mockDetail("ch:", live(mock));
    await screen.findByRole("heading", { level: 2 });
    const card = must(
      screen
        .getAllByRole("listitem")
        .find((li) => li.getAttribute("data-recommendation-id") === rec.id),
    );
    fireEvent.change(within(card).getByLabelText("Reason"), {
      target: { value: "ok" },
    });
    fireEvent.click(
      within(card).getByRole("button", { name: "Accept recommendation" }),
    );
    fireEvent.change(within(card).getByLabelText("Action"), {
      target: { value: "Fit a check." },
    });
    fireEvent.click(within(card).getByRole("button", { name: "Edit action" }));
    await vi.waitFor(() =>
      expect(fake.calls.filter((c) => c.method === "POST").length).toBe(2),
    );
    expect(
      fake.calls.filter((c) => c.method === "POST").map((c) => c.body),
    ).toEqual([
      {
        target_id: rec.id,
        action: "accept",
        new_value: null,
        reason: "ok",
        by: "B",
      },
      {
        target_id: rec.id,
        action: "edit",
        new_value: { action: "Fit a check." },
        reason: "ok",
        by: "B",
      },
    ]);
  });

  it("show the known limit next to change credit (PROJECT.md section 23)", async () => {
    mockDetail("f:m:S-MX-1:more:temperature:", live(mock));
    expect(
      await screen.findByText(
        "No override to say a layer applies and let code re-check its credit.",
      ),
    ).toBeDefined();
  });
});

describe("the demo moment on the WG final run (C2)", () => {
  function demoDetail(after: () => FakeResponse) {
    const list = { run_id: DEMO_RUN, label: LIVE, items: [demo.item] };
    let posted = false;
    const fake = fakeFetch({
      [`/runs/${enc(DEMO_RUN)}/shortlist`]: () =>
        posted ? after() : { body: list },
      [`POST /runs/${enc(DEMO_RUN)}/overrides`]: () => {
        posted = true;
        return { body: { override: {}, stored: true } };
      },
      [`/runs/${enc(DEMO_RUN)}`]: { body: demo.run_detail },
      [`/plants/${enc(demo.plant_detail.plant_record_id)}`]: {
        body: demo.plant_detail,
      },
    });
    render(
      <AppProvider client={new ApiClient("", fake.impl)}>
        <Shell
          route={{
            name: "item",
            runId: DEMO_RUN,
            targetId: demo.item.target_id,
          }}
        >
          <Detail runId={DEMO_RUN} targetId={demo.item.target_id} />
        </Shell>
      </AppProvider>,
    );
    return fake;
  }

  it("shows the 1.6× evidence with its cited facts traced", async () => {
    demoDetail(() => ({ body: {} }));
    const card = must(
      (await screen.findAllByRole("article")).find((a) =>
        a.textContent?.includes("at least 1.6× design"),
      ),
    );
    const traced = Array.from(card.querySelectorAll("[data-record-id]")).map(
      (b) => b.getAttribute("data-record-id"),
    );
    for (const id of must(demo.item.evidence?.[0]).fact_ids ?? [])
      expect(traced).toContain(id);
  });

  it("shows the RV-PATH-EA425B layer's stored reason verbatim, uncredited", async () => {
    demoDetail(() => ({ body: {} }));
    const layer = must(
      demo.item.lopa?.layers?.find((l) => l.layer_id === "RV-PATH-EA425B"),
    );
    const table = await screen.findByRole("table", {
      name: "Protection layers",
    });
    const row = must(
      within(table)
        .getAllByRole("row")
        .find((r) => r.getAttribute("data-layer-id") === layer.layer_id),
    );
    expect(row.textContent).toContain(layer.reason);
    expect(row.classList.contains("refused")).toBe(true);
  });

  it("shows the description as stored, keys named, its unexpected character flagged", async () => {
    // Q7 (2026-10-25): the stored text, its record keys shown as names (raw on hover); undoing
    // every name gives the stored text back, so nothing of the model's words is cleaned (C2)
    demoDetail(() => ({ body: {} }));
    const description = must(demo.item.chain?.description);
    expect(description.endsWith("that互")).toBe(true);
    const named = nameKeys(description);
    expect(undoNames(named)).toBe(description);
    const shown = await screen.findByText(
      (_, el) => el?.classList.contains("description") === true,
    );
    expect(shown.textContent).toBe(named.text);
    expect(shown.textContent?.endsWith("that互")).toBe(true);
    // one traced span, so the text wraps as a sentence; each named key keeps its raw key on hover
    expect(shown.querySelectorAll("button.traced")).toHaveLength(1);
    const keys = Array.from(shown.querySelectorAll("abbr.named-key")).map((a) =>
      a.getAttribute("title"),
    );
    for (const part of named.parts)
      if (part.key) expect(keys).toContain(part.key);
    expect(
      screen.getByText(
        "unexpected character in model text: U+4E92 (chain description)",
      ),
    ).toBeDefined();
  });

  it("shows the chain's reason with its keys named, raw on hover (F6)", async () => {
    demoDetail(() => ({ body: {} }));
    const reason = must(demo.item.chain?.reason);
    const named = nameKeys(reason);
    expect(undoNames(named)).toBe(reason);
    const shown = must(
      (
        await screen.findAllByText(
          (_, el) => el?.classList.contains("reason") === true,
        )
      ).find((el) => el.textContent.includes("creates heat input")),
    );
    expect(shown.textContent).toBe(named.text);
    expect(shown.textContent).not.toContain("proc:P-REB-START-2:early");
    const keys = Array.from(shown.querySelectorAll("abbr.named-key")).map((a) =>
      a.getAttribute("title"),
    );
    expect(keys).toContain("proc:P-REB-START-2:early");
    expect(keys).toContain("EA-425B.design_pressure_kpa");
  });

  it("opens HV-B-SIN.normal_position in the drawer with its value and source", async () => {
    demoDetail(() => ({ body: {} }));
    const links = await screen.findByRole("list", { name: "Links" });
    fireEvent.click(
      must(
        within(links)
          .getAllByRole("button")
          .find(
            (b) =>
              b.getAttribute("data-record-id") === "HV-B-SIN.normal_position",
          ),
      ),
    );
    const drawer = await screen.findByRole("dialog", { name: /plant fact/i });
    expect(await within(drawer).findByText("closed")).toBeDefined();
    expect(
      within(drawer).getByText("CSB case study p. 15 fn. 21, p. 32"),
    ).toBeDefined();
  });

  it("changes S3 to S4 with exactly the change-severity body, then shows the server's gap and order", async () => {
    window.localStorage.setItem("guideword.engineer", "B. Engineer");
    const recomputed = {
      ...demo.item,
      gap: 10000,
      gap_text:
        "about 10,000× tolerable — mitigated about 1 in 10 years, tolerable about 1 in 100,000 years",
    };
    const fake = demoDetail(() => ({
      body: { run_id: DEMO_RUN, label: LIVE, items: [recomputed] },
    }));
    expect(await screen.findByText(must(demo.item.gap_text))).toBeDefined();
    fireEvent.change(screen.getByLabelText("New severity"), {
      target: { value: "S4" },
    });
    fireEvent.change(screen.getByLabelText("Reason for the severity"), {
      target: { value: "The reboiler bay is staffed during startup." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Change severity" }));
    expect(await screen.findByText(recomputed.gap_text)).toBeDefined();
    expect(
      fake.calls.filter((c) => c.method === "POST").map((c) => c.body),
    ).toEqual([
      {
        target_id: demo.item.target_id,
        action: "change_severity",
        new_value: { severity_class: "S4" },
        reason: "The reboiler bay is staffed during startup.",
        by: "B. Engineer",
      },
    ]);
  });
});
