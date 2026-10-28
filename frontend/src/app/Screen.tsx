// The screen a route names. A route whose screen is not built yet says what comes next and where
// to go instead, never a placeholder (Bhargavi, 2026-10-27).

import { Coverage } from "../screens/Coverage";
import { Detail } from "../screens/Detail";
import { Live } from "../screens/Live";
import { RunStart } from "../screens/RunStart";
import { Shortlist } from "../screens/Shortlist";
import { ExportLinks } from "../ui/ExportLinks";
import { buildHash, type Route } from "./router";

const PLANT_TITLES = {
  plants: "Plants",
  plant: "Plant input",
  sections: "Sections",
} as const;

export function Screen({ route }: { route: Route }) {
  if (route.name === "not_found") {
    return (
      <section>
        <h2>Not found</h2>
        <p>No screen at {route.path}.</p>
      </section>
    );
  }
  if (route.name === "runs") return <RunStart />;
  if (route.name === "live") return <Live runId={route.runId} />;
  if (route.name === "shortlist") return <Shortlist runId={route.runId} />;
  if (route.name === "coverage") return <Coverage runId={route.runId} />;
  if (route.name === "item")
    return <Detail runId={route.runId} targetId={route.targetId} />;
  if (route.name === "worksheet") {
    return (
      <section>
        <h2>Worksheet</h2>
        <ExportLinks runId={route.runId} />
        <p>
          The full worksheet is in the Excel file; an on-screen worksheet is
          next.
        </p>
      </section>
    );
  }
  return (
    <section>
      <h2>{PLANT_TITLES[route.name]}</h2>
      <p>
        Plant input and sections are next. Each recorded run is on the{" "}
        <a href={buildHash({ name: "runs" })}>runs list</a>.
      </p>
    </section>
  );
}
