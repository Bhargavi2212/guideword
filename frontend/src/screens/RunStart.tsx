// The runs screen (spec 5.3, P5-8): the runs so far, each opening its live view or replay, and
// the start form. The use comes from `Budget.api_run_uses`, shown with its remaining amount and
// the phase's; the spend cap and post cap are typed in, never pre-filled, and Start is refused,
// with the reason, until spend cap + post cap fits both. Confirming is built into the page.

import { useState } from "react";

import { ApiError } from "../api/client";
import { useResource } from "../api/hooks";
import type {
  Budget,
  PlantList,
  RunList,
  StartRunRequest,
  StartRunResult,
} from "../api/schema";
import { useApp } from "../app/context";
import { buildHash } from "../app/router";
import { money } from "../format/number";
import { startCheck, type BudgetUseName } from "../model/runStart";
import { ConfirmInline } from "../ui/ConfirmInline";
import { CostLine } from "../ui/CostLine";

type Started = { runId: string; estimate: number };

function StartForm({ budget, plants }: { budget: Budget; plants: PlantList }) {
  const { client } = useApp();
  const ready = plants.plants.filter((p) => p.status === "sections_confirmed");
  const [plant, setPlant] = useState(ready[0]?.plant_record_id ?? "");
  const [use, setUse] = useState<BudgetUseName | "">(
    budget.api_run_uses[0] ?? "",
  );
  const [spendCap, setSpendCap] = useState("");
  const [postCap, setPostCap] = useState("");
  const [sent, setSent] = useState<{ busy: boolean; error: string | null }>({
    busy: false,
    error: null,
  });
  const [started, setStarted] = useState<Started | null>(null);

  const check = use === "" ? null : startCheck(budget, use, spendCap, postCap);
  const refusals = [
    ...(plant === "" ? ["No plant has confirmed sections."] : []),
    ...(use === "" ? ["No use is offered to runs started here."] : []),
    ...(check?.refusals ?? []),
  ];

  const start = () => {
    if (use === "" || check === null || check.maximum === null) return;
    const body: StartRunRequest = {
      plant_id: plant,
      spend_cap_usd: Number(spendCap),
      post_spend_cap_usd: Number(postCap),
      mode: "full",
      use,
    };
    setSent({ busy: true, error: null });
    client.post<StartRunResult>("/runs", body).then(
      (result) => {
        setSent({ busy: false, error: null });
        setStarted({
          runId: result.run_id,
          estimate: result.estimated_cost_usd,
        });
      },
      (error: unknown) =>
        setSent({
          busy: false,
          error: error instanceof ApiError ? error.detail : String(error),
        }),
    );
  };

  if (started !== null)
    return (
      <p className="run-started" role="status">
        {`Run started: estimated cost ${money(started.estimate)}. `}
        <a href={buildHash({ name: "live", runId: started.runId })}>
          Watch it live
        </a>
      </p>
    );

  return (
    <form
      className="start-run"
      aria-label="Start a run"
      onSubmit={(e) => e.preventDefault()}
    >
      <label>
        Plant
        <select value={plant} onChange={(e) => setPlant(e.target.value)}>
          {ready.map((p) => (
            <option key={p.plant_record_id} value={p.plant_record_id}>
              {p.plant_id}
            </option>
          ))}
        </select>
      </label>
      <label>
        Use
        <select
          value={use}
          onChange={(e) => setUse(e.target.value as BudgetUseName)}
        >
          {budget.api_run_uses.map((u) => (
            <option key={u} value={u}>
              {u}
            </option>
          ))}
        </select>
      </label>
      {check !== null ? (
        <p className="start-left">
          {`${use}: ${check.useLeft === null ? "no allowance here" : `${money(check.useLeft)} left`}. Phase ${check.phase.phase}: ${money(check.phase.remaining_usd)} left of ${money(check.phase.cap_usd)} (up to ${money(check.phase.remaining_usd)} this phase).`}
        </p>
      ) : null}
      <label>
        Spend cap (USD)
        <input
          inputMode="decimal"
          value={spendCap}
          onChange={(e) => setSpendCap(e.target.value)}
        />
      </label>
      <label>
        Post cap (USD)
        <input
          inputMode="decimal"
          value={postCap}
          onChange={(e) => setPostCap(e.target.value)}
        />
      </label>
      {check?.maximum != null && spendCap !== "" && postCap !== "" ? (
        <CostLine spendCapUsd={Number(spendCap)} postCapUsd={Number(postCap)} />
      ) : null}
      {refusals.length > 0 ? (
        <ul className="refusals" aria-label="Why Start is refused">
          {refusals.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      ) : null}
      <ConfirmInline
        label="Start run"
        question={`Start a full run that can spend up to ${money(check?.maximum ?? 0)}?`}
        onConfirm={start}
        disabled={refusals.length > 0 || sent.busy}
      />
      {sent.error !== null ? <p role="alert">{sent.error}</p> : null}
    </form>
  );
}

export function RunStart() {
  const runs = useResource<RunList>("/runs");
  const budget = useResource<Budget>("/budget");
  const plants = useResource<PlantList>("/plants");
  return (
    <section>
      <h2>Runs</h2>
      {runs.error !== null ? (
        <p role="alert">{`Runs could not be loaded: ${runs.error.detail}`}</p>
      ) : null}
      {runs.data !== null ? (
        <table className="run-list">
          <thead>
            <tr>
              <th>Run</th>
              <th>Plant</th>
              <th>Status</th>
              <th>Spent</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {runs.data.runs.map((run) => (
              <tr key={run.id}>
                <td>{run.id}</td>
                <td>{run.plant_record_id}</td>
                <td>{run.status.replace(/_/g, " ")}</td>
                <td>{money(run.spent_usd)}</td>
                <td>
                  <a href={buildHash({ name: "live", runId: run.id })}>
                    {run.status === "running" ? "Watch" : "Replay"}
                  </a>{" "}
                  <a href={buildHash({ name: "shortlist", runId: run.id })}>
                    Shortlist
                  </a>{" "}
                  <a href={buildHash({ name: "coverage", runId: run.id })}>
                    Coverage
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      {/* where live runs are off (the public site), there is no start form at all (F6) */}
      {budget.error !== null || plants.error !== null ? (
        <>
          <h3>Start a run</h3>
          <p role="alert">
            {`The start form could not be loaded: ${(budget.error ?? plants.error)?.detail ?? ""}`}
          </p>
        </>
      ) : budget.data?.live_run_available === true ? (
        <>
          <h3>Start a run</h3>
          {plants.data !== null ? (
            <StartForm budget={budget.data} plants={plants.data} />
          ) : (
            <p className="muted">Loading…</p>
          )}
        </>
      ) : null}
    </section>
  );
}
