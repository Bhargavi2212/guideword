// The screen a route names. F0 ships the shell; each screen arrives in its own PR (spec 5.1–5.7),
// so until then a route shows its name and which PR builds it.

import { Shortlist } from "../screens/Shortlist";
import type { Route } from "./router";

const TITLES: Record<Exclude<Route["name"], "not_found">, [string, string]> = {
  plants: ["Plants", "F5"],
  plant: ["Plant input", "F5"],
  sections: ["Sections", "F5"],
  runs: ["Runs", "F3"],
  live: ["Live run", "F3"],
  shortlist: ["Shortlist", "F1"],
  item: ["Finding detail", "F2"],
  worksheet: ["Worksheet", "F4"],
  coverage: ["Coverage", "F4"],
};

export function Screen({ route }: { route: Route }) {
  if (route.name === "not_found") {
    return (
      <section>
        <h2>Not found</h2>
        <p>No screen at {route.path}.</p>
      </section>
    );
  }
  if (route.name === "shortlist") return <Shortlist runId={route.runId} />;
  const [title, pr] = TITLES[route.name];
  return (
    <section>
      <h2>{title}</h2>
      <p className="placeholder">This screen arrives with {pr}.</p>
    </section>
  );
}
