// The deployed site's landing (deploy plan D3; review plan R3, Q9): an empty hash opens the
// default run's shortlist (the picker's first, WG), with its demo moment marked "start here".
// A plant picker offers the site's other recorded runs in the server's order, and each run
// shows its own banner, written by Bhargavi; only a run with a start line has "start here".

import type { DemoResponse } from "../api/schema";
import type { Route } from "./router";

export type DemoRun = DemoResponse["runs"][number];

const EMPTY = new Set(["", "#", "#/"]);

/** Where the landing goes, or null to stay on the route the hash names. */
export function landingRoute(
  hash: string,
  demo: DemoResponse | null,
): Route | null {
  if (demo === null || !EMPTY.has(hash)) return null;
  return { name: "shortlist", runId: demo.run.run.id };
}

/** The picker's runs, in the server's order (the default first). */
export function pickerRuns(demo: DemoResponse | null): DemoRun[] {
  return demo?.runs ?? [];
}

/** This run's entry in the site's runs, if the site offers it. */
export function demoRun(
  demo: DemoResponse | null,
  runId: string,
): DemoRun | null {
  return pickerRuns(demo).find((r) => r.run_id === runId) ?? null;
}

/** The line marked "start here" on this run's shortlist, if the site names one. */
export function startTarget(
  demo: DemoResponse | null,
  runId: string,
): string | null {
  if (demo === null) return null;
  const entry = demoRun(demo, runId);
  if (entry !== null) return entry.start_target_id ?? null;
  // a response from before contract v1.11: the default run only
  if (demo.run.run.id !== runId) return null;
  return demo.start_target_id ?? null;
}

/** The banner Bhargavi wrote for this run, if any. */
export function bannerFor(
  demo: DemoResponse | null,
  runId: string,
): string | null {
  return demoRun(demo, runId)?.banner ?? null;
}

/** Where a plant chosen in the header goes: its first run's shortlist in the runs list, or the
 * runs list when it has none (plant input is not on the site yet; Bhargavi, 2026-10-27). */
export function plantRoute(
  plantId: string,
  runs: readonly { id: string; plant_record_id: string }[],
): Route {
  const first = runs.find((r) => r.plant_record_id === plantId);
  return first ? { name: "shortlist", runId: first.id } : { name: "runs" };
}
