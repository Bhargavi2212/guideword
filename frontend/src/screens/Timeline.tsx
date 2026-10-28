// The run's timeline (spec 5.3): newest at the bottom, each step with its decisions, dispatch,
// model calls (tier chip, job, cache hit, cost) and findings; the run's own events between.
// It follows new events unless the reader has scrolled up.

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { clock } from "../format/time";
import {
  eventLine,
  gapBefore,
  groupTimeline,
  recordIdOf,
  tierChip,
  type ApiEvent,
  type StepGroup,
} from "../model/timeline";
import { Traced } from "../ui/Traced";

// within this many pixels of the bottom counts as at the bottom
const FOLLOW_SLACK_PX = 24;

function TierChip({ event }: { event: ApiEvent }) {
  const chip = tierChip(event);
  if (chip === null) return null;
  return (
    <span
      className={`chip chip-tier chip-tier-${chip.tier ?? "unknown"}${chip.source === "inferred" ? " chip-tier-inferred" : ""}`}
    >
      {chip.text}
    </span>
  );
}

function Line({ event }: { event: ApiEvent }) {
  const id = recordIdOf(event);
  const text = eventLine(event);
  return (
    <span className={`tl-line tl-${event.type}`} data-seq={event.seq}>
      <TierChip event={event} />
      {id === null ? text : <Traced id={id}>{text}</Traced>}
    </span>
  );
}

function Gap({ text }: { text: string | null }) {
  return text === null ? null : <li className="tl-gap">{text}</li>;
}

function Step({ group }: { group: StepGroup }) {
  const dispatched = group.rows.some((r) => r.type === "dispatch");
  return (
    <li className="tl-step">
      <div className="tl-step-head">
        <time>{clock(group.started.time)}</time>
        <Line event={group.started} />
      </div>
      {group.rows.length > 0 ? (
        <ul className="tl-rows">
          {group.rows.map((e) => (
            <li key={e.seq}>
              <Line event={e} />
            </li>
          ))}
        </ul>
      ) : null}
      {group.calls.length > 0 ? (
        <div className="tl-calls">
          <span className="tl-label">
            {`${String(group.calls.length)} model call${group.calls.length === 1 ? "" : "s"}${dispatched ? " for this dispatch" : ""}`}
          </span>
          <ul>
            {group.calls.map((e) => (
              <li key={e.seq}>
                <Line event={e} />
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {group.findings.length > 0 ? (
        <details className="tl-findings">
          <summary>
            {`${String(group.findings.length)} finding${group.findings.length === 1 ? "" : "s"} added`}
          </summary>
          <ul>
            {group.findings.map((e) => (
              <li key={e.seq}>
                <Line event={e} />
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      {group.finished ? (
        <div className="tl-step-foot">
          <Line event={group.finished} />
        </div>
      ) : null}
    </li>
  );
}

export function Timeline({ events }: { events: readonly ApiEvent[] }) {
  const items = useMemo(() => groupTimeline(events), [events]);
  // the gap mark before each item, from the event shown just before it
  const gaps = useMemo(() => {
    const at = new Map(events.map((e, n) => [e.seq, n]));
    return items.map((item) => gapBefore(events, at.get(item.seq) ?? 0));
  }, [events, items]);
  const box = useRef<HTMLOListElement>(null);
  const [follow, setFollow] = useState(true);

  useLayoutEffect(() => {
    const el = box.current;
    if (el !== null && follow) el.scrollTop = el.scrollHeight;
  }, [events, follow]);
  useEffect(() => {
    const el = box.current;
    if (el === null) return;
    const onScroll = () =>
      setFollow(
        el.scrollTop + el.clientHeight >= el.scrollHeight - FOLLOW_SLACK_PX,
      );
    el.addEventListener("scroll", onScroll);
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <ol ref={box} className="timeline" aria-label="Timeline">
      {items.map((item, n) => [
        <Gap key={`gap-${String(item.seq)}`} text={gaps[n] ?? null} />,
        item.kind === "step" ? (
          <Step key={item.seq} group={item} />
        ) : (
          <li key={item.seq} className="tl-event">
            <time>{clock(item.event.time)}</time>
            <Line event={item.event} />
          </li>
        ),
      ])}
    </ol>
  );
}
