// The traceability drawer (P5-6): a record with its parents, model calls and tool calls; a plant
// fact with its value and source. Fact IDs resolve from the plant's facts (C11).

import { useResource } from "../api/hooks";
import type { PlantDetail, RecordDetail } from "../api/schema";
import { isFactId } from "../format/ids";
import { money } from "../format/number";
import { Traced } from "./Traced";

const enc = encodeURIComponent;

type Props = {
  runId: string | null;
  plantId: string | null;
  recordId: string;
  onClose: () => void;
};

export function RecordDrawer(props: Props) {
  return isFactId(props.recordId) ? (
    <FactPanel {...props} />
  ) : (
    <RecordPanel {...props} />
  );
}

function Panel({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <aside role="dialog" aria-label={title} className="drawer">
      <header className="drawer-head">
        <h2>{title}</h2>
        <button type="button" onClick={onClose} aria-label="Close">
          ×
        </button>
      </header>
      {children}
    </aside>
  );
}

function shown(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value);
}

function FactPanel({ plantId, recordId, onClose }: Props) {
  const plant = useResource<PlantDetail>(
    plantId === null ? null : `/plants/${enc(plantId)}`,
  );
  const fact = plant.data?.facts.find((f) => f.id === recordId) ?? null;
  return (
    <Panel title={`Plant fact ${recordId}`} onClose={onClose}>
      <p className="id">{recordId}</p>
      {plant.loading ? <p>Loading…</p> : null}
      {!plant.loading && fact === null ? (
        <p>not stated in the plant file</p>
      ) : null}
      {fact !== null ? (
        <dl>
          <dt>Value</dt>
          <dd>{shown(fact.value)}</dd>
          <dt>Source</dt>
          <dd>
            <span className={fact.source === "assumed" ? "assumed" : undefined}>
              {fact.source}
            </span>
          </dd>
        </dl>
      ) : null}
    </Panel>
  );
}

function RecordPanel({ runId, recordId, onClose }: Props) {
  const path =
    runId === null ? null : `/runs/${enc(runId)}/records/${enc(recordId)}`;
  const detail = useResource<RecordDetail>(path);
  const record = detail.data;
  if (record === null) {
    return (
      <Panel title={`Record ${recordId}`} onClose={onClose}>
        <p className="id">{recordId}</p>
        {detail.error !== null && detail.error.status === 404 ? (
          <p>not addressable yet</p>
        ) : null}
        {detail.error !== null && detail.error.status !== 404 ? (
          <p>{detail.error.detail}</p>
        ) : null}
        {detail.loading ? <p>Loading…</p> : null}
      </Panel>
    );
  }
  // its scalar fields; the ID is shown above, and lists open from the sections below
  const fields = Object.entries(record.record).filter(
    ([key, value]) =>
      key !== "id" && (value === null || typeof value !== "object"),
  );
  return (
    <Panel
      title={`${record.record_kind} ${record.record_id}`}
      onClose={onClose}
    >
      <p className="id">{record.record_id}</p>
      <dl>
        {fields.map(([key, value]) => (
          <div key={key}>
            <dt>{key}</dt>
            <dd>{shown(value)}</dd>
          </div>
        ))}
      </dl>
      {record.parent_ids.length > 0 ? (
        <section>
          <h3>Came from</h3>
          <ul>
            {record.parent_ids.map((id) => (
              <li key={id}>
                <Traced id={id}>{id}</Traced>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {record.model_calls.length > 0 ? (
        <section>
          <h3>Model calls</h3>
          <ul>
            {record.model_calls.map((call) => (
              <li key={call.id}>
                <Traced id={call.id}>
                  {call.model_id} · {call.tier ?? "unknown"} ·{" "}
                  {money(call.cost_usd)}
                </Traced>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {record.tool_calls.length > 0 ? (
        <section>
          <h3>Tool calls</h3>
          <ul>
            {record.tool_calls.map((call) => (
              <li key={call.id}>
                <Traced id={call.id}>
                  {call.tool}
                  {call.refused_reason
                    ? ` — refused: ${call.refused_reason}`
                    : ""}
                </Traced>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </Panel>
  );
}
