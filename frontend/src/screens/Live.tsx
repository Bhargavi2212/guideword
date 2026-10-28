// Screen 3, the live run (spec 5.3, P5-4). A running run is followed live, its events asked for
// every 2 s; a run that has ended is replayed from its stored events, in order, at the chosen
// speed, under a banner that says so. The side panel and the end state read only the events
// shown so far and the run record.

import { useMemo, useState } from "react";

import { ApiError } from "../api/client";
import { usePolling } from "../api/hooks";
import type { RunDetail, RunStatusResult } from "../api/schema";
import { useEvents, type EventsMode } from "../api/useEvents";
import { useApp } from "../app/context";
import { buildHash } from "../app/router";
import { useReplay } from "../app/useReplay";
import { money } from "../format/number";
import { day } from "../format/time";
import {
  SPEEDS,
  endState,
  findingsCount,
  latestCoverage,
  modelMix,
  replayDelays,
  spentSoFar,
  type ApiEvent,
  type Speed,
} from "../model/timeline";
import { Timeline } from "./Timeline";

export const RUN_EVERY_MS = 2000;
const DEFAULT_SPEED: Speed = 60;

const speedText = (speed: Speed) =>
  speed === "max" ? "max speed" : `${String(speed)}×`;

function SidePanel({
  detail,
  events,
}: {
  detail: RunDetail;
  events: readonly ApiEvent[];
}) {
  const coverage = latestCoverage(events);
  const mix = modelMix(events);
  const run = detail.run;
  return (
    <aside className="live-panel" aria-label="Run so far">
      <h3>Coverage</h3>
      {coverage === null ? (
        <p className="muted">No coverage yet.</p>
      ) : (
        <ul className="coverage-bars">
          {coverage.map((line) => (
            <li key={line.list}>
              <span className="bar-name">{line.list.replace(/_/g, " ")}</span>
              <meter
                min={0}
                max={Math.max(line.total, 1)}
                value={line.checked}
              />
              <span className="bar-count">
                {`${String(line.checked)} of ${String(line.total)}`}
                {line.unsure > 0 ? `, ${String(line.unsure)} unsure` : ""}
                {line.failed > 0 ? `, ${String(line.failed)} failed` : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
      <h3>Findings</h3>
      <p data-testid="findings-count">{String(findingsCount(events))}</p>
      <h3>Spend</h3>
      <p data-testid="spend">
        {`${money(spentSoFar(events))} in the calls shown, of up to ${money(run.spend_cap_usd + run.post_spend_cap_usd)} (spend cap ${money(run.spend_cap_usd)} + post cap ${money(run.post_spend_cap_usd)})`}
      </p>
      <h3>Model mix</h3>
      {mix.length === 0 ? (
        <p className="muted">No model calls yet.</p>
      ) : (
        <table className="model-mix">
          <thead>
            <tr>
              <th>Tier</th>
              <th>Calls</th>
              <th>Cost</th>
            </tr>
          </thead>
          <tbody>
            {mix.map((row) => (
              <tr key={row.tier}>
                <td>
                  {row.tier}
                  {row.inferred > 0 ? " (inferred)" : ""}
                </td>
                <td>{String(row.calls)}</td>
                <td>{money(row.cost_usd)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </aside>
  );
}

export function Live({ runId }: { runId: string }) {
  const { client } = useApp();
  const [running, setRunning] = useState(false);
  const detail = usePolling<RunDetail>(
    `/runs/${encodeURIComponent(runId)}`,
    RUN_EVERY_MS,
    running,
  );
  const status = detail.data?.run.status ?? null;
  const nowRunning = status === "running" || status === "draft";
  if (status !== null && nowRunning !== running) setRunning(nowRunning);

  // chosen once, from the status first seen: a run that ends while watched stays live
  const [mode, setMode] = useState<{ runId: string; mode: EventsMode } | null>(
    null,
  );
  if (status !== null && mode?.runId !== runId)
    setMode({ runId, mode: nowRunning ? "live" : "replay" });
  const current = mode?.runId === runId ? mode.mode : null;

  const events = useEvents(runId, current, nowRunning);
  const [speed, setSpeed] = useState<Speed>(DEFAULT_SPEED);
  const delays = useMemo(
    () => (current === "replay" ? replayDelays(events.events, speed) : null),
    [current, events.events, speed],
  );
  const replay = useReplay(delays);
  const shown = useMemo(
    () =>
      current === "replay"
        ? events.events.slice(0, replay.shown)
        : events.events,
    [current, events.events, replay.shown],
  );
  const [cancel, setCancel] = useState<{ busy: boolean; error: string | null }>(
    {
      busy: false,
      error: null,
    },
  );

  if (detail.error !== null)
    return (
      <section>
        <h2>Live run</h2>
        <p role="alert">{`The run could not be loaded: ${detail.error.detail}`}</p>
      </section>
    );
  if (detail.data === null || current === null)
    return (
      <section>
        <h2>Live run</h2>
        <p className="muted">Loading the run…</p>
      </section>
    );

  const data = detail.data;
  const label = data.label;
  const played =
    current === "replay"
      ? events.complete && replay.shown >= events.events.length
      : true;
  const end = played ? endState(data.run, shown) : null;

  const sendCancel = () => {
    setCancel({ busy: true, error: null });
    client
      .post<RunStatusResult>(`/runs/${encodeURIComponent(runId)}/cancel`)
      .then(
        () => {
          setCancel({ busy: false, error: null });
          detail.reload();
        },
        (error: unknown) =>
          setCancel({
            busy: false,
            error: error instanceof ApiError ? error.detail : String(error),
          }),
      );
  };

  return (
    <section className="live">
      <h2>{current === "replay" ? "Replay" : "Live run"}</h2>
      {current === "replay" ? (
        <>
          <p className="replay-banner" role="note">
            {`Replay of a finished run — recorded ${day(label.recorded_at ?? events.events.at(-1)?.time)}, cost ${money(label.cost_usd ?? data.run.spent_usd)}, shown at ${speedText(speed)}`}
          </p>
          <div
            className="replay-controls"
            role="group"
            aria-label="Replay speed"
          >
            {SPEEDS.map((s) => (
              <button
                key={String(s)}
                type="button"
                aria-pressed={s === speed}
                onClick={() => setSpeed(s)}
              >
                {s === "max" ? "max" : `${String(s)}×`}
              </button>
            ))}
            <button type="button" onClick={replay.jumpToEnd} disabled={played}>
              Jump to end
            </button>
          </div>
        </>
      ) : null}
      {current === "live" && nowRunning ? (
        <p className="live-controls">
          <button type="button" onClick={sendCancel} disabled={cancel.busy}>
            Cancel run
          </button>
          {cancel.error !== null ? (
            <span role="alert">{cancel.error}</span>
          ) : null}
        </p>
      ) : null}
      {events.error !== null ? (
        <p role="alert">{`Events could not be loaded: ${events.error.detail}`}</p>
      ) : null}
      <div className="live-body">
        <Timeline events={shown} />
        <SidePanel detail={data} events={shown} />
      </div>
      {end !== null ? (
        <p className={`end-state end-${end.kind}`} role="status">
          {end.text}{" "}
          <a href={buildHash({ name: "shortlist", runId })}>
            Open the shortlist
          </a>
        </p>
      ) : null}
    </section>
  );
}
