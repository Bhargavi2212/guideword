// A line's evidence (spec 5.2): one card per record, its summary verbatim (P5-5), every fact it
// used and every fact it lacked traced, its sources opening in a new tab, its judge traced. A
// calculation card names its equipment; a skipped one is one line, its missing facts expandable
// (Bhargavi's review, 2026-10-25).

import type { Evidence } from "../api/schema";
import { calculationOf, isSkipped, skippedLine } from "../model/evidence";
import { Chip } from "../ui/Chip";
import { Flags } from "../ui/Flags";
import { Traced } from "../ui/Traced";

export function EvidenceCards({ evidence }: { evidence: readonly Evidence[] }) {
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
                  <span key={id}>
                    <Traced id={id}>{id}</Traced>{" "}
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

function CardHeader({ evidence: e }: { evidence: Evidence }) {
  const ref = calculationOf(e);
  return (
    <header>
      <span className="kind">
        {ref === null ? e.kind : `${e.kind} on ${ref.equipment_id}`}
      </span>{" "}
      <Chip kind="verdict" value={e.verdict} />
    </header>
  );
}

/** "Heat-up time skipped: 11 plant facts missing", the facts listed when opened. */
function SkippedCard({ evidence: e }: { evidence: Evidence }) {
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
