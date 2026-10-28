import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import coverageJson from "../../../contract/fixtures/coverage.json";
import createdJson from "../../../contract/fixtures/question_created.json";
import questionsJson from "../../../contract/fixtures/question_list.json";
import sectionsJson from "../../../contract/fixtures/run_sections.json";
import { ApiClient } from "../api/client";
import type {
  Coverage as CoverageBody,
  QuestionCreated,
  QuestionList,
  RunSections,
} from "../api/schema";
import { AppProvider } from "../app/context";
import { fakeFetch, type FakeResponse } from "../test/fakeFetch";
import { fixture } from "../test/fixtures";
import { Coverage } from "./Coverage";

const coverage = fixture<CoverageBody>(coverageJson);
const questions = fixture<QuestionList>(questionsJson);
const sections = fixture<RunSections>(sectionsJson);
const created = fixture<QuestionCreated>(createdJson);
const RUN = coverage.run_id;
const base = `/runs/${encodeURIComponent(RUN)}`;
const LIVE = { kind: "live" as const, recorded_at: null, cost_usd: null };
const RECORDED = {
  kind: "recorded" as const,
  recorded_at: "2026-10-23T04:41:18Z",
  cost_usd: 0.9,
};

const engineerList = (label = questions.label): QuestionList => ({
  ...questions,
  label,
  questions: questions.questions.filter((q) => q.kind === "engineer"),
});

function mount(
  routes: Record<string, FakeResponse | (() => FakeResponse)> = {},
) {
  const fake = fakeFetch({
    [`${base}/coverage`]: { body: coverage },
    [`${base}/questions?status=failed`]: { body: questions },
    [`${base}/questions?kind=engineer`]: { body: engineerList() },
    [`${base}/sections`]: { body: sections },
    [`POST ${base}/questions`]: { body: created },
    [`POST ${base}/overrides`]: { body: { override: {}, stored: true } },
    ...routes,
  });
  render(
    <AppProvider client={new ApiClient("", fake.impl)}>
      <Coverage runId={RUN} />
    </AppProvider>,
  );
  return fake;
}

afterEach(() => {
  window.localStorage.clear();
});

describe("the coverage table (spec 5.4)", () => {
  it("shows one row per served list with its checked, total, unsure and failed", async () => {
    mount();
    const table = await screen.findByRole("table", { name: "Coverage" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((r) => r.getAttribute("data-list"))).toEqual(
      coverage.lists.map((l) => l.list),
    );
    const planned = rows[6];
    expect(planned?.textContent).toContain("Planned work");
    expect(
      within(planned as HTMLElement)
        .getAllByRole("cell")
        .map((c) => c.textContent?.trim()),
    ).toEqual(["0 of 1", "0", "1"]);
    const bar = within(planned as HTMLElement).getByRole("meter");
    expect(bar.getAttribute("value")).toBe("0");
    expect(bar.getAttribute("max")).toBe("1");
  });

  it("totals the questions at the top, and the sections apart", async () => {
    mount();
    expect((await screen.findByTestId("coverage-total")).textContent).toBe(
      "Checked 97 of 99 questions · 7 of 9 sections",
    );
  });
});

describe("failed questions", () => {
  it("lists each failed question traced, with its text", async () => {
    mount();
    const list = await screen.findByRole("list", { name: "Failed questions" });
    await within(list).findByText(/Planned job W-1/);
    const traced = within(list)
      .getAllByRole("button")
      .map((b) => b.getAttribute("data-record-id"));
    expect(traced).toEqual(coverage.failed_question_ids);
  });

  it("says when no question failed", async () => {
    mount({
      [`${base}/coverage`]: {
        body: { ...coverage, failed_question_ids: [] },
      },
    });
    expect(await screen.findByText("No question failed.")).toBeTruthy();
  });
});

describe("engineer questions", () => {
  const form = () => screen.getByRole("form", { name: "Add a question" });

  it("posts a section and text, then lists the question as open", async () => {
    const fake = mount({
      [`${base}/questions?kind=engineer`]: {
        body: { ...engineerList(), questions: [] },
      },
    });
    await screen.findByRole("option", { name: /S-L-12 / });
    fireEvent.change(within(form()).getByLabelText("Section"), {
      target: { value: "S-L-12" },
    });
    fireEvent.change(within(form()).getByLabelText("Question"), {
      target: { value: created.question.text },
    });
    fireEvent.click(within(form()).getByRole("button", { name: "Add" }));
    const list = screen.getByRole("list", { name: "Engineer questions" });
    const row = await within(list).findByText(created.question.text);
    expect(
      fake.calls.find(
        (c) => c.method === "POST" && c.path.endsWith("/questions"),
      )?.body,
    ).toEqual({ section_id: "S-L-12", text: created.question.text });
    const item = row.closest("li") as HTMLElement;
    expect(item.textContent).toContain("open");
    expect(
      item.querySelector("[data-record-id]")?.getAttribute("data-record-id"),
    ).toBe(created.question.id);
  });

  it("does not add without a section and text", async () => {
    mount();
    await screen.findByRole("option", { name: /S-L-12 / });
    const add = within(form()).getByRole("button", { name: "Add" });
    expect((add as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(within(form()).getByLabelText("Question"), {
      target: { value: "Can HV-12 stay open?" },
    });
    expect((add as HTMLButtonElement).disabled).toBe(true);
  });

  it("refuses on a recorded run, sending nothing", async () => {
    const fake = mount({
      [`${base}/coverage`]: { body: { ...coverage, label: RECORDED } },
    });
    expect(
      await within(
        await screen.findByRole("form", { name: "Add a question" }),
      ).findByText("This run is recorded and read-only"),
    ).toBeTruthy();
    expect(
      (within(form()).getByRole("button", { name: "Add" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect(fake.calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("answers an open question with the answer override", async () => {
    window.localStorage.setItem("guideword.engineer", "B. Engineer");
    const fake = mount({
      [`${base}/coverage`]: { body: { ...coverage, label: LIVE } },
      [`${base}/questions?kind=engineer`]: { body: engineerList(LIVE) },
    });
    const list = await screen.findByRole("list", {
      name: "Engineer questions",
    });
    const answer = await within(list).findByLabelText("Answer");
    fireEvent.change(answer, { target: { value: "Yes, with P-1 isolated." } });
    fireEvent.click(within(list).getByRole("button", { name: "Save answer" }));
    await screen.findByText("Answer saved.");
    expect(
      fake.calls.find(
        (c) => c.method === "POST" && c.path.endsWith("/overrides"),
      )?.body,
    ).toEqual({
      target_id: "eng:S-L-12:ca86fcc92907c1f2",
      action: "answer",
      new_value: { text: "Yes, with P-1 isolated." },
      reason: "the engineer's answer to their question",
      by: "B. Engineer",
    });
  });

  it("does not answer on a mock run, and says why", async () => {
    window.localStorage.setItem("guideword.engineer", "B. Engineer");
    mount();
    const list = await screen.findByRole("list", {
      name: "Engineer questions",
    });
    await within(list).findByText("This is mock data: nothing is saved");
    expect(within(list).queryByLabelText("Answer")).toBeNull();
  });
});
