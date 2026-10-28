// A LOPA as a staircase on a log axis (review plan R4): from the initiating frequency, a step
// down for each credited layer labelled with its stored PFD, an uncredited layer crossed out with
// its reason, to the stored mitigated frequency; the tolerable line and the gap marked. Hand-drawn
// SVG; every number is the served record's, and the layers are listed, traced, under the picture.

import type { LopaRecord } from "../api/schema";
import { frequency, pfd } from "../format/number";
import { gapTimes } from "../model/technical";
import { lopaBar } from "../model/visuals";
import { Traced } from "./Traced";

const WIDTH = 640;
const HEIGHT = 200;
const LEFT = 64;
const RIGHT = 120;
const TOP = 14;
const BOTTOM = 34;

export function LopaBar({ lopa }: { lopa: LopaRecord }) {
  const bar = lopaBar(lopa);
  if (bar === null) return null;
  const columns = bar.steps.length + 2;
  const colW = (WIDTH - LEFT - RIGHT) / columns;
  const x = (n: number) => LEFT + n * colW;
  const y = (log: number) =>
    TOP +
    ((bar.log_max - log) / (bar.log_max - bar.log_min)) *
      (HEIGHT - TOP - BOTTOM);
  const startLog = Math.log10(bar.start.per_year);
  const endLog =
    bar.mitigated_per_year !== null && bar.mitigated_per_year > 0
      ? Math.log10(bar.mitigated_per_year)
      : (bar.steps.at(-1)?.log_after ?? startLog);
  const tolLog = Math.log10(bar.tolerable_per_year);

  // the staircase: flat across each column, down at each credited layer
  let path = `M ${String(x(0))} ${String(y(startLog))} H ${String(x(1))}`;
  bar.steps.forEach((s, n) => {
    path += ` V ${String(y(s.log_after))} H ${String(x(n + 2))}`;
  });
  path += ` V ${String(y(endLog))} H ${String(x(columns))}`;

  const ticks: number[] = [];
  for (let t = bar.log_max; t >= bar.log_min; t--) ticks.push(t);
  const gap = gapTimes(bar.gap);
  // the picture's margin holds the short form; the caption says it in full
  const short =
    bar.gap !== null && bar.gap > 1
      ? `${Number(bar.gap.toPrecision(2)).toLocaleString("en-US")}× over`
      : "";

  return (
    <figure className="lopa-bar">
      {/* the picture opens the LOPA record, so every number in it is traced (P5-6) */}
      <Traced id={bar.lopa_id}>
        <svg
          viewBox={`0 0 ${String(WIDTH)} ${String(HEIGHT)}`}
          role="img"
          aria-label={`LOPA: ${frequency(bar.start.per_year)} at the start, ${frequency(bar.mitigated_per_year)} mitigated, tolerable ${frequency(bar.tolerable_per_year)}`}
        >
          {ticks.map((t) => (
            <g key={t} className="lopa-tick">
              <line x1={LEFT} x2={x(columns)} y1={y(t)} y2={y(t)} />
              <text x={LEFT - 6} y={y(t) + 4} textAnchor="end">
                {frequency(10 ** t)}
              </text>
            </g>
          ))}
          <line
            className="lopa-tolerable"
            x1={LEFT}
            x2={x(columns)}
            y1={y(tolLog)}
            y2={y(tolLog)}
          />
          <text
            className="lopa-tolerable-label"
            x={x(columns) + 6}
            y={y(tolLog) + 4}
          >
            {`tolerable ${frequency(bar.tolerable_per_year)}`}
          </text>
          <path className="lopa-stair" d={path} />
          {bar.steps.map((s, n) => (
            <g
              key={s.layer_id}
              className={
                s.credited ? "lopa-layer" : "lopa-layer lopa-uncredited"
              }
            >
              <text x={x(n + 1) + colW / 2} y={HEIGHT - 18} textAnchor="middle">
                {s.layer_id}
              </text>
              {s.credited ? (
                <text
                  className="lopa-pfd"
                  x={x(n + 1) + 4}
                  y={
                    (y(s.log_after) +
                      y(bar.steps[n - 1]?.log_after ?? startLog)) /
                    2
                  }
                >
                  {`PFD ${pfd(s.pfd)}`}
                </text>
              ) : (
                <line
                  className="lopa-cross"
                  x1={x(n + 1) + 6}
                  x2={x(n + 2) - 6}
                  y1={HEIGHT - 22}
                  y2={HEIGHT - 22}
                />
              )}
            </g>
          ))}
          <text x={x(0) + colW / 2} y={HEIGHT - 18} textAnchor="middle">
            start
          </text>
          <text
            x={x(columns - 1) + colW / 2}
            y={HEIGHT - 18}
            textAnchor="middle"
          >
            mitigated
          </text>
          {endLog > tolLog ? (
            <g className="lopa-gap">
              <line
                x1={x(columns) - 8}
                x2={x(columns) - 8}
                y1={y(endLog)}
                y2={y(tolLog)}
              />
              <text x={x(columns) + 6} y={(y(endLog) + y(tolLog)) / 2 + 4}>
                {short}
              </text>
            </g>
          ) : null}
        </svg>
      </Traced>
      <figcaption>
        <ol className="lopa-steps" aria-label="LOPA steps">
          <li data-step="start">
            <Traced id={bar.lopa_id}>
              {`${bar.start.label}: ${frequency(bar.start.per_year)}`}
            </Traced>
          </li>
          {bar.steps.map((s) => (
            <li
              key={s.layer_id}
              data-step={s.layer_id}
              className={s.credited ? undefined : "lopa-uncredited"}
            >
              <Traced id={bar.lopa_id}>
                {s.credited ? (
                  `${s.layer_id}: credited, PFD ${pfd(s.pfd)}`
                ) : (
                  <>
                    <s>{s.layer_id}</s>
                    {`: not credited: ${s.reason}`}
                  </>
                )}
              </Traced>
            </li>
          ))}
          <li data-step="end">
            <Traced id={bar.lopa_id}>
              {`mitigated ${frequency(bar.mitigated_per_year)} against tolerable ${frequency(bar.tolerable_per_year)}: ${gap}`}
            </Traced>
          </li>
        </ol>
      </figcaption>
    </figure>
  );
}
