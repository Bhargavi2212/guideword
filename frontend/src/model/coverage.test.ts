import { describe, expect, it } from "vitest";

import coverageJson from "../../../contract/fixtures/coverage.json";
import questionsJson from "../../../contract/fixtures/question_list.json";
import type { Coverage, QuestionList } from "../api/schema";
import { fixture } from "../test/fixtures";
import { coverageTotals, failedRows, listName } from "./coverage";

const coverage = fixture<Coverage>(coverageJson);
const questions = fixture<QuestionList>(questionsJson).questions;

describe("coverage lists (spec 5.4)", () => {
  it("names every list the spec names", () => {
    expect(coverage.lists.map((l) => listName(l.list))).toEqual([
      "Sections",
      "Matrix",
      "Chemical pairs",
      "Chemical environment",
      "No-flow lines",
      "Procedure steps",
      "Planned work",
      "Dust",
      "Relief discharge",
      "Added by AI",
      "Engineer",
    ]);
  });

  it("shows an unknown list by its served key", () => {
    expect(listName("new_list")).toBe("new list");
  });

  it("totals the question lists, and the sections line on its own", () => {
    // the mock: 79+1+6+0+10+1+0+1+0+1 = 99 questions, 79+1+6+10+1 = 97 checked; 7 of 9 sections
    expect(coverageTotals(coverage.lists)).toEqual({
      questions: { checked: 97, total: 99 },
      sections: { checked: 7, total: 9 },
    });
  });

  it("has no sections total when the sections line is missing", () => {
    const lists = coverage.lists.filter((l) => l.list !== "sections");
    expect(coverageTotals(lists).sections).toBeNull();
  });
});

describe("failed questions", () => {
  it("lists each failed ID in served order with its text", () => {
    expect(failedRows(coverage.failed_question_ids, questions)).toEqual([
      {
        id: "work:W-1:PSV-1",
        text: "Planned job W-1 (hot work) and PSV-1: what could the work affect or be affected by, and are the existing isolation and protection adequate?",
      },
    ]);
  });

  it("keeps a failed ID whose question did not load, with no text", () => {
    expect(failedRows(["m:S-X:more:flow"], [])).toEqual([
      { id: "m:S-X:more:flow", text: null },
    ]);
  });
});
