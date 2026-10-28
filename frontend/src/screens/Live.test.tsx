import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import pageJson from "../../../contract/fixtures/events_page.json";
import failedJson from "../../../contract/fixtures/events_page_failed.json";
import runJson from "../../../contract/fixtures/run_detail.json";
import { ApiClient } from "../api/client";
import type { EventsPage, RunDetail } from "../api/schema";
import { AppProvider } from "../app/context";
import { fakeFetch, type FakeResponse } from "../test/fakeFetch";
import { fixture } from "../test/fixtures";
import { latestCoverage, type ApiEvent } from "../model/timeline";
import { Live } from "./Live";
import { Timeline } from "./Timeline";

const page = fixture<EventsPage>(pageJson);
const failedPage = fixture<EventsPage>(failedJson);
const detail = fixture<RunDetail>(runJson);
const RUN = detail.run.id;
const enc = encodeURIComponent;
const RUN_PATH = `/runs/${enc(RUN)}`;
const eventsPath = (after: number) =>
  `${RUN_PATH}/events?after=${String(after)}`;

const withStatus = (status: RunDetail["run"]["status"]): RunDetail => ({
  ...detail,
  run: { ...detail.run, status },
});
const pageOf = (events: ApiEvent[], after: number): EventsPage => ({
  ...page,
  events,
  next_after: events.at(-1)?.seq ?? after,
});

// effects (the replay's next timer) run when an act ends, so time passes in small steps
const TICK_MS = 20;

/** Lets the fake fetches resolve and `ms` of fake time pass. */
async function pass(ms = 0) {
  let left = ms;
  do {
    const step = Math.min(left, TICK_MS);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(step);
    });
    left -= step;
  } while (left > 0);
}

/** The events on screen, by seq (a step shows its calls after its other rows). */
function shownSeqs(): number[] {
  return Array.from(document.querySelectorAll(".timeline [data-seq]"))
    .map((e) => Number(e.getAttribute("data-seq")))
    .sort((a, b) => a - b);
}

function mount(routes: Record<string, FakeResponse | (() => FakeResponse)>) {
  const fake = fakeFetch(routes);
  render(
    <AppProvider client={new ApiClient("", fake.impl)}>
      <Live runId={RUN} />
    </AppProvider>,
  );
  return fake;
}

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
  Object.defineProperty(document, "visibilityState", {
    value: "visible",
    configurable: true,
  });
});

describe("replay of a finished run (P5-4)", () => {
  function replay(events: EventsPage = page, run: RunDetail = detail) {
    const last = events.events.at(-1)?.seq ?? 0;
    return mount({
      [RUN_PATH]: { body: run },
      [eventsPath(0)]: { body: events },
      [eventsPath(last)]: { body: pageOf([], last) },
    });
  }

  it("is chosen for a finished run, under a banner that says so", async () => {
    replay();
    await pass();
    expect(screen.getByRole("heading", { level: 2 }).textContent).toBe(
      "Replay",
    );
    expect(screen.getByRole("note").textContent).toMatch(
      /^Replay of a finished run — recorded \d{4}-\d{2}-\d{2}, cost .+, shown at 60×$/,
    );
    expect(screen.queryByRole("button", { name: "Cancel run" })).toBeNull();
  });

  it("plays the events in seq order, none skipped or added, and the banner stays", async () => {
    replay();
    await pass();
    const all = page.events.map((e) => e.seq);
    let before = 0;
    for (let n = 0; n < 20; n++) {
      await pass(200);
      const seqs = shownSeqs();
      // a gapless start of the run's events, each once
      expect(seqs).toEqual(all.slice(0, seqs.length));
      expect(seqs.length).toBeGreaterThanOrEqual(before);
      before = seqs.length;
      expect(screen.getByRole("note")).toBeTruthy();
    }
    expect(before).toBeGreaterThan(1);
  });

  it("keeps the order when the speed changes, and the banner names the speed", async () => {
    replay();
    await pass(1000);
    fireEvent.click(screen.getByRole("button", { name: "10×" }));
    expect(screen.getByRole("note").textContent).toMatch(/shown at 10×$/);
    await pass(3000);
    fireEvent.click(screen.getByRole("button", { name: "max" }));
    expect(screen.getByRole("note").textContent).toMatch(/shown at max speed$/);
    // one event a tick here; in a browser each comes MAX_STEP_MS after the last
    await pass(TICK_MS * page.events.length);
    expect(shownSeqs()).toEqual(page.events.map((e) => e.seq));
    // every event at max takes one fake tick each: slow under a full parallel run
  }, 30_000);

  it("jumps to the end: every event, then the end state", async () => {
    replay();
    await pass();
    expect(screen.queryByRole("status")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Jump to end" }));
    await pass(EVENTS_WAIT);
    expect(shownSeqs()).toEqual(page.events.map((e) => e.seq));
    expect(screen.getByRole("status").textContent).toMatch(
      /^Finished: spent <\$0\.01\./,
    );
  });

  it("names the step a failed run failed at", async () => {
    replay(failedPage, withStatus("failed"));
    await pass();
    fireEvent.click(screen.getByRole("button", { name: "Jump to end" }));
    await pass(EVENTS_WAIT);
    expect(screen.getByRole("status").textContent).toMatch(
      /^Failed at the analysis step/,
    );
  });

  it("fills the side panel from the events shown", async () => {
    replay();
    await pass();
    fireEvent.click(screen.getByRole("button", { name: "Jump to end" }));
    await pass(EVENTS_WAIT);
    const lines = latestCoverage(page.events) ?? [];
    const names = Array.from(
      document.querySelectorAll(".coverage-bars .bar-name"),
    ).map((e) => e.textContent);
    expect(names).toEqual(lines.map((l) => l.list.replace(/_/g, " ")));
    expect(screen.getByTestId("findings-count").textContent).toBe(
      String(page.events.filter((e) => e.type === "finding_added").length),
    );
    expect(screen.getByTestId("spend").textContent).toBe(
      "<$0.01 in the calls shown, of up to $0.30 (spend cap $0.20 + post cap $0.10)",
    );
    expect(
      document.querySelectorAll(".model-mix tbody tr").length,
    ).toBeGreaterThan(0);
  });
});

// the events hook's next ask, after a page
const EVENTS_WAIT = 2100;

describe("a running run, followed live", () => {
  function running() {
    let status: RunDetail["run"]["status"] = "running";
    const first = page.events.slice(0, 50);
    const rest = page.events.slice(50);
    const fake = mount({
      [RUN_PATH]: () => ({ body: withStatus(status) }),
      [eventsPath(0)]: { body: pageOf(first, 0) },
      [eventsPath(50)]: { body: pageOf(rest, 50) },
      [eventsPath(page.next_after)]: { body: pageOf([], page.next_after) },
    });
    const asks = () =>
      fake.calls.filter((c) => c.path.includes("/events")).length;
    return { fake, asks, end: () => (status = "finished") };
  }

  it("shows each new page as it comes, with no replay banner", async () => {
    running();
    await pass();
    expect(screen.getByRole("heading", { level: 2 }).textContent).toBe(
      "Live run",
    );
    expect(screen.queryByRole("note")).toBeNull();
    expect(shownSeqs()).toEqual(page.events.slice(0, 50).map((e) => e.seq));
    await pass(EVENTS_WAIT);
    expect(shownSeqs()).toEqual(page.events.map((e) => e.seq));
  });

  it("stops asking once the run has ended", async () => {
    const run = running();
    await pass(EVENTS_WAIT * 2);
    run.end();
    await pass(EVENTS_WAIT * 2);
    const after = run.asks();
    await pass(EVENTS_WAIT * 5);
    expect(run.asks()).toBe(after);
    expect(screen.getByRole("status").textContent).toMatch(/^Finished/);
  });

  it("stops asking while the tab is hidden", async () => {
    const run = running();
    await pass();
    Object.defineProperty(document, "visibilityState", {
      value: "hidden",
      configurable: true,
    });
    const before = run.asks();
    await pass(EVENTS_WAIT * 5);
    expect(run.asks()).toBe(before);
  });

  it("cancels the run with the cancel button", async () => {
    const run = running();
    await pass();
    fireEvent.click(screen.getByRole("button", { name: "Cancel run" }));
    await pass();
    expect(run.fake.calls).toContainEqual({
      method: "POST",
      path: `${RUN_PATH}/cancel`,
      body: null,
    });
  });
});

describe("auto-scroll", () => {
  function sized(el: HTMLElement, height: number) {
    Object.defineProperty(el, "scrollHeight", {
      value: height,
      configurable: true,
    });
    Object.defineProperty(el, "clientHeight", {
      value: 100,
      configurable: true,
    });
  }

  it("follows new events unless the reader has scrolled up", () => {
    vi.useRealTimers();
    const { rerender } = render(
      <AppProvider client={new ApiClient("", fakeFetch({}).impl)}>
        <Timeline events={page.events.slice(0, 10)} />
      </AppProvider>,
    );
    const box = screen.getByRole("list", { name: "Timeline" });
    sized(box, 1000);
    const show = (n: number) =>
      rerender(
        <AppProvider client={new ApiClient("", fakeFetch({}).impl)}>
          <Timeline events={page.events.slice(0, n)} />
        </AppProvider>,
      );
    show(20);
    expect(box.scrollTop).toBe(1000);
    box.scrollTop = 0;
    fireEvent.scroll(box);
    sized(box, 2000);
    show(30);
    expect(box.scrollTop).toBe(0);
  });
});
