import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ApiClient } from "../api/client";
import type { LopaRecord, ShortlistItem } from "../api/schema";
import { AppProvider } from "../app/context";
import { fakeFetch } from "../test/fakeFetch";
import demoJson from "../test/fixtures/wg_demo_item.json";
import { must } from "../test/must";
import { ChainFlow } from "./ChainFlow";
import { LopaBar } from "./LopaBar";

type Demo = {
  item: ShortlistItem;
  plant_detail: { facts: { id: string; value: unknown }[] };
};
const demo = demoJson as unknown as Demo;
const chain = must(demo.item.chain);
const lopa = must(demo.item.lopa);
const facts = Object.fromEntries(
  demo.plant_detail.facts.map((f) => [f.id, f.value]),
);

function show(node: React.ReactNode) {
  return render(
    <AppProvider client={new ApiClient("", fakeFetch({}).impl)}>
      {node}
    </AppProvider>,
  );
}

describe("ChainFlow on the WG chain (R4)", () => {
  it("draws a box per link in the stored order, each opening its own record", () => {
    show(
      <ChainFlow
        links={chain.links}
        factValues={facts}
        evidence={demo.item.evidence ?? []}
      />,
    );
    const boxes = within(
      screen.getByRole("list", { name: "Chain flow" }),
    ).getAllByRole("listitem");
    expect(boxes.map((b) => b.getAttribute("data-link"))).toEqual(chain.links);
    for (const box of boxes)
      expect(
        box.querySelector("[data-record-id]")?.getAttribute("data-record-id"),
      ).toBe(box.getAttribute("data-link"));
  });

  it("shows the four valves closed, in the closed style and in words", () => {
    show(<ChainFlow links={chain.links} factValues={facts} evidence={[]} />);
    const closed = Array.from(document.querySelectorAll(".flow-closed"));
    expect(closed.map((b) => b.getAttribute("data-link"))).toEqual([
      "HV-QW-B-IN.normal_position",
      "HV-QW-B-OUT.normal_position",
      "HV-B-SIN.normal_position",
      "HV-B-SOUT.normal_position",
    ]);
    for (const box of closed) expect(box.textContent).toContain("closed");
  });
});

describe("LopaBar on the WG LOPA (R4)", () => {
  it("lists the start, each layer as stored, and the end against the limit", () => {
    show(<LopaBar lopa={lopa} />);
    const steps = within(screen.getByRole("list", { name: "LOPA steps" }))
      .getAllByRole("listitem")
      .map((li) => li.textContent);
    expect(steps[0]).toBe("IE-HE-MONTHLY: 0.1 /yr");
    expect(steps[1]).toMatch(/^RV-PATH-EA425B: not credited: does not apply/);
    expect(steps[2]).toBe(
      "mitigated 0.1 /yr against tolerable 1e-4 /yr: 1,000× over the risk limit",
    );
    expect(document.querySelector(".lopa-uncredited s")?.textContent).toBe(
      "RV-PATH-EA425B",
    );
  });

  it("labels each credited step with its stored PFD", () => {
    const credited: LopaRecord = {
      ...lopa,
      layers: [
        {
          layer_id: "SIF-1",
          layer_type: "SIF",
          credited: true,
          pfd: 0.01,
          reason: "ok",
        },
      ],
      mitigated_frequency_per_year: 0.001,
      gap: 10,
    };
    show(<LopaBar lopa={credited} />);
    expect(document.querySelector(".lopa-pfd")?.textContent).toBe("PFD 0.01");
  });

  it("moves the tolerable line with the served LOPA after a severity override", () => {
    const { rerender } = show(<LopaBar lopa={lopa} />);
    const label = () =>
      document.querySelector(".lopa-tolerable-label")?.textContent;
    const at = () =>
      document.querySelector(".lopa-tolerable")?.getAttribute("y1");
    expect(label()).toBe("tolerable 1e-4 /yr");
    const before = at();
    rerender(
      <AppProvider client={new ApiClient("", fakeFetch({}).impl)}>
        <LopaBar
          lopa={{
            ...lopa,
            severity_class: "S4",
            tolerable_per_year: 0.00001,
            gap: 10000,
          }}
        />
      </AppProvider>,
    );
    expect(label()).toBe("tolerable 1e-5 /yr");
    expect(at()).not.toBe(before);
  });
});
