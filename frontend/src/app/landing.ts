// The deployed site's landing (deploy plan D3): an empty hash opens the demo run's shortlist,
// with its demo moment marked "start here". F3's PR moves the landing to the replay.

import type { DemoResponse } from "../api/schema";
import type { Route } from "./router";

const EMPTY = new Set(["", "#", "#/"]);

/** Where the landing goes, or null to stay on the route the hash names. */
export function landingRoute(
  hash: string,
  demo: DemoResponse | null,
): Route | null {
  if (demo === null || !EMPTY.has(hash)) return null;
  return { name: "shortlist", runId: demo.run.run.id };
}

/** The line marked "start here" on this run's shortlist, if this is the demo run. */
export function startTarget(
  demo: DemoResponse | null,
  runId: string,
): string | null {
  if (demo === null || demo.run.run.id !== runId) return null;
  return demo.start_target_id ?? null;
}
