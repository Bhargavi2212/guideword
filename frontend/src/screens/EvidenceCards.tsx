// A line's evidence (spec 5.2): one card per record, its summary verbatim (P5-5), every fact it
// used and every fact it lacked traced, its sources opening in a new tab, its judge traced. A
// calculation card names its equipment; a skipped one is one line, its missing facts expandable
// (Bhargavi's review, 2026-10-25). It also says what it is attached through (`via_ids`, the
// line's links that brought it) and shows each fact it used with the plant's value (review plan
// R3), the fact's name in words and its raw ID on hover.

import type { ShortlistEvidence } from "../api/schema";
import { calculationOf, isSkipped, skippedLine } from "../model/evidence";
import { keyName } from "../model/names";
import { Chip } from "../ui/Chip";
import { Flags } from "../ui/Flags";
import { Traced } from "../ui/Traced";

export function EvidenceCards({
  evidence,
  factValues = {},
}: {
  evidence: readonly ShortlistEvidence[];
  // the plant's facts, by fact ID, as the plant file stores them
  factValues?: Record<string, unknown>;
}) {
  if (evidence.length === 0)
    return <p className="placeholder">No evidence on this line.</p>;
  return (
    <div className="evidence">
      {evidence.map((e) =>
        isSkipped(e) ? (
          <SkippedCard key={e.id} evidence={e} />
        ) : (
          <article key={e.id} className="evidence-card" data-evidence-id={e.id}>
            <CardHeader evidence={e} />
            <p>
              <Traced id={e.id}>{e.summary}</Traced>
            </p>
            {(e.fact_ids ?? []).length > 0 ? (
              <p className="facts">
                Facts used:{" "}
                {(e.fact_ids ?? []).map((id) => (
                  <span key={id} className="fact-used">
                    <Traced id={id}>
                      {id in factValues
                        ? `${keyName(id)} = ${shown(factValues[id])}`
                        : keyName(id)}
                    </Traced>{" "}
                  </span>
                ))}
              </p>
            ) : null}
            {(e.missing_fact_ids ?? []).length > 0 ? (
              <p className="facts">
                Missing:{" "}
                {(e.missing_fact_ids ?? []).map((id) => (
                  <span key={id}>
                    <Traced id={id}>{id}</Traced>{" "}
                  </span>
                ))}
              </p>
            ) : null}
            {(e.sources ?? []).length > 0 ? (
              <ul className="sources">
                {(e.sources ?? []).map((url) => (
                  <li key={url}>
                    <a href={url} target="_blank" rel="noopener noreferrer">
                      {url}
                    </a>
                  </li>
                ))}
              </ul>
            ) : null}
            {e.model_call_id ? (
              <p>
                <Traced id={e.model_call_id}>the judge's call</Traced>
              </p>
            ) : null}
            <Flags flags={e.flags ?? []} traceId={e.id} />
          </article>
        ),
      )}
    </div>
  );
}

function CardHeader({ evidence: e }: { evidence: ShortlistEvidence }) {
  const ref = calculationOf(e);
  const via = e.via_ids ?? [];
  return (
    <header>
      <span className="kind">
        {ref === null ? e.kind : `${e.kind} on ${ref.equipment_id}`}
      </span>
      {via.length > 0 ? (
        <span className="via">
          {" · via "}
          {via.map((id, n) => (
            <span key={id}>
              {n > 0 ? ", " : ""}
              <Traced id={id}>{keyName(id)}</Traced>
            </span>
          ))}
        </span>
      ) : null}{" "}
      <Chip kind="verdict" value={e.verdict} />
    </header>
  );
}

/** A plant fact's value as text: a list joined, an object as JSON, anything else as itself. */
function shown(value: unknown): string {
  if (Array.isArray(value)) return value.map((v) => shown(v)).join(", ");
  if (value !== null && typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/** "Heat-up time skipped: 11 plant facts missing", the facts listed when opened. */
function SkippedCard({ evidence: e }: { evidence: ShortlistEvidence }) {
  return (
    <article className="evidence-card evidence-skipped" data-evidence-id={e.id}>
      <CardHeader evidence={e} />
      <details>
        <summary>{skippedLine(e)}</summary>
        <ul className="facts" aria-label="Missing facts">
          {(e.missing_fact_ids ?? []).map((id) => (
            <li key={id}>
              <Traced id={id}>{id}</Traced>
            </li>
          ))}
        </ul>
        <p>
          <Traced id={e.id}>the calculation's record</Traced>
        </p>
      </details>
      <Flags flags={e.flags ?? []} traceId={e.id} />
    </article>
  );
}
