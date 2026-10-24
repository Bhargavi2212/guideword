import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LabelBanner } from "./LabelBanner";

describe("LabelBanner", () => {
  it("names a live run", () => {
    render(
      <LabelBanner
        label={{ kind: "live", recorded_at: null, cost_usd: null }}
      />,
    );
    expect(screen.getByRole("status").textContent).toBe("Live run");
  });

  it("names a recorded run with its date and cost", () => {
    render(
      <LabelBanner
        label={{
          kind: "recorded",
          recorded_at: "2026-10-22T14:05:00Z",
          cost_usd: 0.8882,
        }}
      />,
    );
    expect(screen.getByRole("status").textContent).toBe(
      "Recorded run — 2026-10-22 — cost $0.89",
    );
  });

  it("names mock data", () => {
    render(
      <LabelBanner
        label={{ kind: "mock", recorded_at: null, cost_usd: null }}
      />,
    );
    expect(screen.getByRole("status").textContent).toBe(
      "Mock data — not a real plant",
    );
  });
});
