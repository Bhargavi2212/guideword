// The header every screen shares (spec 5.0): plant and run selectors, the run's label banner,
// status and step, spend against the cap (traced to the run, C12), the budget, the engineer. On a
// recorded run nothing can be started or overridden, so the budget, the engineer's name and the
// plant status are left out (Bhargavi's review, 2026-10-25).

import type { ReactNode } from "react";

import { useResource } from "../api/hooks";
import type { Budget, PlantList, RunDetail, RunList } from "../api/schema";
import { money } from "../format/number";
import { LabelBanner } from "../ui/LabelBanner";
import { RecordDrawer } from "../ui/RecordDrawer";
import { Traced } from "../ui/Traced";
import { useApp } from "./context";
import { buildHash, type Route } from "./router";

function runOf(route: Route): string | null {
  return "runId" in route ? route.runId : null;
}

function plantOf(route: Route): string | null {
  return "plantId" in route ? route.plantId : null;
}

function go(route: Route): void {
  window.location.hash = buildHash(route);
}

export function Shell({
  route,
  children,
}: {
  route: Route;
  children: ReactNode;
}) {
  const { recordId, closeRecord, engineer, setEngineer } = useApp();
  const runId = runOf(route);
  const plants = useResource<PlantList>("/plants");
  const runs = useResource<RunList>("/runs");
  const run = useResource<RunDetail>(
    runId === null ? null : `/runs/${encodeURIComponent(runId)}`,
  );
  const budget = useResource<Budget>("/budget");
  const plantId = plantOf(route) ?? run.data?.run.plant_record_id ?? null;
  const recorded = run.data?.label.kind === "recorded";

  return (
    <div className="shell">
      <header className="header">
        <h1 className="brand">
          <a href={buildHash({ name: "plants" })}>Guideword</a>
        </h1>
        <label>
          Plant
          <select
            value={plantId ?? ""}
            onChange={(e) => go({ name: "plant", plantId: e.target.value })}
          >
            <option value="" disabled>
              choose a plant
            </option>
            {(plants.data?.plants ?? []).map((p) => (
              <option key={p.plant_record_id} value={p.plant_record_id}>
                {recorded ? p.plant_id : `${p.plant_id} (${p.status})`}
              </option>
            ))}
          </select>
        </label>
        <label>
          Run
          <select
            value={runId ?? ""}
            onChange={(e) => go({ name: "shortlist", runId: e.target.value })}
          >
            <option value="" disabled>
              choose a run
            </option>
            {(runs.data?.runs ?? []).map((r) => (
              <option key={r.id} value={r.id}>
                {r.id} ({r.status})
              </option>
            ))}
          </select>
        </label>
        {run.data !== null ? (
          <>
            <LabelBanner label={run.data.label} />
            <span className="run-state">
              {run.data.run.status} · {run.data.run.step}
            </span>
            <Traced id={run.data.run.id}>
              spent {money(run.data.run.spent_usd)} of{" "}
              {money(run.data.run.spend_cap_usd)} cap
            </Traced>
            {run.data.label.note ? (
              <Traced id={run.data.run.id}>
                <span className="spend-note">{run.data.label.note}</span>
              </Traced>
            ) : null}
          </>
        ) : null}
        {budget.data !== null && !recorded ? (
          <span className="budget" aria-label="Budget">
            {budget.data.uses
              .filter((u) => budget.data?.api_run_uses.includes(u.use))
              .map((u) => `${u.use} ${money(u.remaining_usd)} left`)
              .join(" · ")}
            {` · phase ${budget.data.api_run_phase.phase} ${money(budget.data.api_run_phase.remaining_usd)} left`}
          </span>
        ) : null}
        {recorded ? null : (
          <label>
            Engineer
            <input
              value={engineer}
              placeholder="your name, for overrides"
              onChange={(e) => setEngineer(e.target.value)}
            />
          </label>
        )}
      </header>
      <main className="main">{children}</main>
      {recordId !== null ? (
        <RecordDrawer
          runId={runId}
          plantId={plantId}
          recordId={recordId}
          onClose={closeRecord}
        />
      ) : null}
    </div>
  );
}
