// A run's events (spec 5.3, P5-4), fetched by `next_after`. Live mode asks again every
// `everyMs` while the run is running and the tab is visible, then once more when it ends, so no
// trailing event is missed. Replay mode loads the stored events page by page until a page comes
// back empty, then stops. Events are kept in `seq` order, each once.

import { useEffect, useRef, useState } from "react";

import { useApp } from "../app/context";
import type { ApiEvent } from "../model/timeline";
import { ApiError } from "./client";
import type { EventsPage } from "./schema";

export type EventsMode = "live" | "replay";

export type Events = {
  events: ApiEvent[];
  error: ApiError | null;
  /** replay: every stored event is loaded; live: the run has ended and the last page is in */
  complete: boolean;
};

export const EVENTS_EVERY_MS = 2000;

// an empty page keeps the same array, so nothing that depends on it recomputes
function merge(known: ApiEvent[], page: readonly ApiEvent[]): ApiEvent[] {
  const last = known.at(-1)?.seq ?? 0;
  const fresh = page.filter((e) => e.seq > last).sort((a, b) => a.seq - b.seq);
  return fresh.length === 0 ? known : [...known, ...fresh];
}

/** `mode` null waits (the run is still loading); `running` keeps live mode polling. */
export function useEvents(
  runId: string,
  mode: EventsMode | null,
  running: boolean,
  everyMs: number = EVENTS_EVERY_MS,
): Events {
  const { client } = useApp();
  const [state, setState] = useState<Events & { runId: string }>({
    runId,
    events: [],
    error: null,
    complete: false,
  });
  // where the next page starts, per run; kept across effect restarts
  const after = useRef<{ runId: string; seq: number }>({ runId, seq: 0 });

  useEffect(() => {
    if (mode === null) return;
    if (after.current.runId !== runId) after.current = { runId, seq: 0 };
    let live = true;
    let timer: number | undefined;
    const path = () =>
      `/runs/${encodeURIComponent(runId)}/events?after=${String(after.current.seq)}`;

    const pull = async () => {
      if (document.visibilityState === "hidden" && mode === "live" && running) {
        timer = window.setTimeout(() => void pull(), everyMs);
        return;
      }
      let page: EventsPage;
      try {
        page = await client.get<EventsPage>(path());
      } catch (error: unknown) {
        if (!live) return;
        const failure =
          error instanceof ApiError ? error : new ApiError(0, String(error));
        setState((s) => ({ ...s, runId, error: failure }));
        return;
      }
      if (!live) return;
      const got = page.events.length > 0;
      if (got) after.current = { runId, seq: page.next_after };
      const again = mode === "live" ? running : got;
      setState((s) => ({
        runId,
        events: merge(s.runId === runId ? s.events : [], page.events),
        error: null,
        complete: !again,
      }));
      if (again) timer = window.setTimeout(() => void pull(), everyMs);
    };
    void pull();
    return () => {
      live = false;
      window.clearTimeout(timer);
    };
  }, [client, runId, mode, running, everyMs]);

  if (state.runId !== runId)
    return { events: [], error: null, complete: false };
  return { events: state.events, error: state.error, complete: state.complete };
}
