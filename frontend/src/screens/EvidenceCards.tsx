// A line's evidence (spec 5.2): one card per record, its summary verbatim (P5-5), every fact it
// used and every fact it lacked traced, its sources opening in a new tab, its judge traced.

import type { Evidence } from "../api/schema";
import { Chip } from "../ui/Chip";
import { Flags } from "../ui/Flags";
import { Traced } from "../ui/Traced";

export function EvidenceCards({ evidence }: { evidence: readonly Evidence[] }) {
  if (evidence.length === 0)
    return <p className="placeholder">No evidence on this line.</p>;
  return (
    <div className="evidence">
      {evidence.map((e) => (
        <article key={e.id} className="evidence-card" data-evidence-id={e.id}>
          <header>
            <span className="kind">{e.kind}</span>{" "}
            <Chip kind="verdict" value={e.verdict} />
          </header>
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
      ))}
    </div>
  );
}
