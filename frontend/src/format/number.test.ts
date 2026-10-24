import { describe, expect, it } from "vitest";

import { frequency, money, pfd } from "./number";

describe("frequency (per year, at most 2 significant figures)", () => {
  it.each([
    [0.1, "0.1 /yr"],
    [0.01, "0.01 /yr"],
    [0.001, "0.001 /yr"],
    [0.0012345, "0.0012 /yr"],
    [0.25, "0.25 /yr"],
    [1, "1 /yr"],
    [12.5, "13 /yr"],
    [1e-4, "1e-4 /yr"],
    [1e-5, "1e-5 /yr"],
    [2.5e-6, "2.5e-6 /yr"],
    [3.14159e-7, "3.1e-7 /yr"],
  ])("%s -> %s", (value, text) => {
    expect(frequency(value)).toBe(text);
  });

  it("hides float noise", () => {
    expect(frequency(0.010000000000000002)).toBe("0.01 /yr");
    expect(frequency(0.1 * 0.1)).toBe("0.01 /yr");
    expect(frequency(1.0000000000000001e-5)).toBe("1e-5 /yr");
  });

  it("shows zero and an absent value plainly", () => {
    expect(frequency(0)).toBe("0 /yr");
    expect(frequency(null)).toBe("—");
    expect(frequency(undefined)).toBe("—");
  });
});

describe("pfd (the stored table value, without float noise)", () => {
  it.each([
    [0.1, "0.1"],
    [0.01, "0.01"],
    [0.010000000000000002, "0.01"],
    [0.001, "0.001"],
    [1e-4, "0.0001"],
    [0.05, "0.05"],
    [1, "1"],
  ])("%s -> %s", (value, text) => {
    expect(pfd(value)).toBe(text);
  });

  it("shows an absent PFD as a dash", () => {
    expect(pfd(null)).toBe("—");
  });
});

describe("money (USD)", () => {
  it.each([
    [0.98, "$0.98"],
    [0.5, "$0.50"],
    [1.1035, "$1.10"],
    [12, "$12.00"],
    [0.0052, "<$0.01"],
    [0.000018, "<$0.01"],
    [0, "$0.00"],
  ])("%s -> %s", (value, text) => {
    expect(money(value)).toBe(text);
  });

  it("rounds half a cent up and hides float noise", () => {
    expect(money(0.105)).toBe("$0.11");
    expect(money(0.1 + 0.2)).toBe("$0.30");
  });

  it("shows an absent amount as a dash", () => {
    expect(money(null)).toBe("—");
  });
});
