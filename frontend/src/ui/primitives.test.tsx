import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Chip } from "./Chip";
import { ConfirmInline } from "./ConfirmInline";
import { CostLine } from "./CostLine";
import { Flags } from "./Flags";

describe("Chip", () => {
  it("shows its value and carries its kind and value as classes (state in form, P5-10)", () => {
    render(<Chip kind="severity" value="S4" />);
    const chip = screen.getByText("S4");
    expect(chip.className).toContain("chip-severity");
    expect(chip.className).toContain("chip-severity-S4");
  });
});

describe("Flags", () => {
  it("shows every flag verbatim, in order", () => {
    const flags = [
      "incomplete LOPA: gap unknown",
      "evidence skipped: missing L-12.length_m",
    ];
    render(<Flags flags={flags} />);
    expect(screen.getAllByRole("listitem").map((li) => li.textContent)).toEqual(
      flags,
    );
  });

  it("shows nothing for no flags", () => {
    const { container } = render(<Flags flags={[]} />);
    expect(container.textContent).toBe("");
  });
});

describe("CostLine (C7, Q10)", () => {
  it("shows spend cap + post cap = the maximum", () => {
    render(<CostLine spendCapUsd={0.15} postCapUsd={0.1} />);
    expect(
      screen.getByText("Up to $0.25: spend cap $0.15 + post cap $0.10"),
    ).toBeDefined();
  });
});

describe("ConfirmInline (P5-8)", () => {
  it("asks once on the page, and acts only on confirm", () => {
    const act = vi.fn();
    render(
      <ConfirmInline
        label="Start run"
        question="Spend up to $0.25?"
        onConfirm={act}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Start run" }));
    expect(screen.getByText("Spend up to $0.25?")).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(act).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Start run" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(act).toHaveBeenCalledTimes(1);
  });

  it("never opens a browser dialog", () => {
    const confirm = vi.spyOn(window, "confirm");
    render(<ConfirmInline label="Go" question="Sure?" onConfirm={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Go" }));
    expect(confirm).not.toHaveBeenCalled();
  });
});
