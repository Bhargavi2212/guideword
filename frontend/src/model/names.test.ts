import { describe, expect, it } from "vitest";

import {
  handleFlag,
  keyName,
  nameKeys,
  undoNames,
  unresolvedHandles,
} from "./names";

const FINDING = "f:m:S-EA-425B:more:pressure:super:C22:e53bce019995581b";
const CHAIN =
  "ch:HV-B-SIN.normal_position+f:proc:P-REB-START-2:early:super:C16:126a45a4b13afa1b";

describe("record keys in displayed text become names (review plan Q7)", () => {
  it.each([
    `Shell overpressure, see ${FINDING}.`,
    `Linked to ${CHAIN} and proc:P-REB-START-2:early (step) with HV-B-SIN.normal_position`,
    "pair:PROPANE:WATER and env:C4-HEAVIES:water, then relief:PSV-1 and work:W-1:EA-425B",
    "nf:L-RUNDOWN and dust:SILO-1, also m:S-L-RUNDOWN~E-106:more:pressure",
    "no keys here at all",
    "",
  ])("undoing every substitution gives back the stored text: %s", (text) => {
    expect(undoNames(nameKeys(text))).toBe(text);
  });

  it("names a finding by its object and words", () => {
    expect(keyName(FINDING)).toBe("EA-425B more pressure");
    expect(
      keyName("f:proc:P-REB-START-2:early:super:C16:126a45a4b13afa1b"),
    ).toBe("P-REB-START-2 early");
  });

  it("names a fact by its object and field", () => {
    expect(keyName("HV-B-SIN.normal_position")).toBe(
      "HV-B-SIN normal position",
    );
  });

  it("names a chain by its parts", () => {
    expect(keyName(CHAIN)).toBe(
      "HV-B-SIN normal position and P-REB-START-2 early",
    );
  });

  it("names pairs, environments, relief, no-flow and split sections", () => {
    expect(keyName("pair:PROPANE:WATER")).toBe("PROPANE and WATER");
    expect(keyName("env:C4-HEAVIES:water")).toBe("C4-HEAVIES with water");
    expect(keyName("relief:PSV-1")).toBe("PSV-1 relief");
    expect(keyName("nf:L-RUNDOWN")).toBe("L-RUNDOWN no flow");
    expect(keyName("m:S-L-RUNDOWN~E-106:more:pressure")).toBe(
      "L-RUNDOWN E-106 more pressure",
    );
  });

  it("keeps each original key with its span, for the hover", () => {
    const shown = nameKeys(`see ${FINDING}.`);
    expect(shown.text).toBe("see EA-425B more pressure.");
    expect(shown.parts).toEqual([
      { text: "see " },
      { text: "EA-425B more pressure", key: FINDING },
      { text: "." },
    ]);
  });
});

describe("connector handles the names can't resolve (decisions row 251)", () => {
  it("are found in a chain's own words, after naming", () => {
    expect(
      unresolvedHandles(["L9 and L34 meet", "per P51, P52 and L9 again"]),
    ).toEqual(["L9", "L34", "P51", "P52"]);
  });

  it("are none in text whose keys all name", () => {
    expect(
      unresolvedHandles([`see ${FINDING}`, "EA-425B more pressure"]),
    ).toEqual([]);
  });

  it("make the flag Bhargavi wrote, with the card's own numbers", () => {
    expect(handleFlag(["L9", "P51"])).toBe(
      "Line and step numbers (L9, P51) from the chain-finder’s prompt; not resolved to plant tags in this development run.",
    );
    expect(handleFlag([])).toBeNull();
  });
});
