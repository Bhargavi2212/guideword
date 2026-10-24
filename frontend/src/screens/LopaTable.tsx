// The LOPA of one line (spec 5.2): initiating event, each layer with Ultra's argument kept apart
// from code's credit, the frequencies, the gap as the server wrote it, and what is missing.

import type { LopaRecord } from "../api/schema";
import { frequency, pfd } from "../format/number";
import { appliesText, layerRows } from "../model/lopa";
import { Flags } from "../ui/Flags";
import { Traced } from "../ui/Traced";

// PROJECT.md section 23: what the change-credit control cannot do
export const CREDIT_LIMIT =
  "No override to say a layer applies and let code re-check its credit.";

type Props = {
  lopa: LopaRecord;
  gapText: string | null;
  // the credit override for a layer, or null while overrides are refused
  onCredit: ((layerId: string, credited: boolean) => void) | null;
};

export function LopaTable({ lopa, gapText, onCredit }: Props) {
  return (
    <section className="lopa" aria-labelledby="lopa-title">
      <h3 id="lopa-title">LOPA</h3>
      <p>
        Initiating event{" "}
        <Traced id={lopa.id}>
          {lopa.initiating_event_id ?? "none"} at{" "}
          {frequency(lopa.initiating_frequency_per_year)}
        </Traced>
        {lopa.frequency_assumed ? (
          <span className="assumed"> assumed</span>
        ) : null}
      </p>
      <table aria-label="Protection layers">
        <thead>
          <tr>
            <th scope="col">Layer</th>
            <th scope="col">Ultra says</th>
            <th scope="col">Code credits</th>
            {onCredit !== null ? <th scope="col">Engineer</th> : null}
          </tr>
        </thead>
        <tbody>
          {layerRows(lopa).map((row) => (
            <tr
              key={row.layerId}
              data-layer-id={row.layerId}
              className={row.credited ? "credited" : "refused"}
            >
              <td>
                <Traced id={row.layerId}>{row.layerId}</Traced>
                {row.layerType ? (
                  <span className="layer-type"> {row.layerType}</span>
                ) : null}
              </td>
              <td data-column="ultra">
                <strong>{appliesText(row.applies)}</strong>
                {row.argument ? <p>{row.argument}</p> : null}
              </td>
              <td data-column="code">
                <strong>
                  {row.credited ? `credited, PFD ${pfd(row.pfd)}` : "no credit"}
                </strong>
                <p>
                  <Traced id={lopa.id}>{row.reason}</Traced>
                </p>
              </td>
              {onCredit !== null ? (
                <td>
                  <button
                    type="button"
                    onClick={() => onCredit(row.layerId, !row.credited)}
                  >
                    {row.credited ? "Withdraw credit" : "Credit this layer"}
                  </button>
                </td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="note">{CREDIT_LIMIT}</p>
      <dl>
        <dt>Mitigated</dt>
        <dd>
          <Traced id={lopa.id}>
            {frequency(lopa.mitigated_frequency_per_year)}
          </Traced>
        </dd>
        <dt>Tolerable</dt>
        <dd>
          <Traced id={lopa.id}>{frequency(lopa.tolerable_per_year)}</Traced>
        </dd>
        <dt>Gap</dt>
        <dd>{gapText ? <Traced id={lopa.id}>{gapText}</Traced> : "unknown"}</dd>
      </dl>
      {(lopa.missing_fact_ids ?? []).length > 0 ? (
        <>
          <h4 id="missing-title">Missing facts</h4>
          <ul aria-labelledby="missing-title">
            {(lopa.missing_fact_ids ?? []).map((id) => (
              <li key={id}>
                <Traced id={id}>{id}</Traced>
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {(lopa.modifiers_not_applied ?? []).length > 0 ? (
        <>
          <h4>Modifiers not applied</h4>
          <ul>
            {(lopa.modifiers_not_applied ?? []).map((m) => (
              <li key={m.kind}>
                {m.kind}: {m.reason}
              </li>
            ))}
          </ul>
        </>
      ) : null}
      <Flags flags={lopa.flags ?? []} traceId={lopa.id} />
    </section>
  );
}
