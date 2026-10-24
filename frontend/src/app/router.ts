// Hash routes (spec 5.0): any static host serves them, with no server rewrites. Every ID is
// URL-encoded, since IDs contain `:`, `~`, `+` and `.`.

export type Route =
  | { name: "plants" }
  | { name: "plant"; plantId: string }
  | { name: "sections"; plantId: string }
  | { name: "runs" }
  | { name: "live"; runId: string }
  | { name: "shortlist"; runId: string }
  | { name: "item"; runId: string; targetId: string }
  | { name: "worksheet"; runId: string }
  | { name: "coverage"; runId: string }
  | { name: "not_found"; path: string };

const RUN_VIEWS = ["live", "shortlist", "worksheet", "coverage"] as const;
type RunView = (typeof RUN_VIEWS)[number];

const enc = encodeURIComponent;

export function buildHash(route: Route): string {
  switch (route.name) {
    case "plants":
      return "#/plants";
    case "plant":
      return `#/plants/${enc(route.plantId)}`;
    case "sections":
      return `#/plants/${enc(route.plantId)}/sections`;
    case "runs":
      return "#/runs";
    case "item":
      return `#/runs/${enc(route.runId)}/items/${enc(route.targetId)}`;
    case "not_found":
      return `#${route.path}`;
    default:
      return `#/runs/${enc(route.runId)}/${route.name}`;
  }
}

function isRunView(part: string): part is RunView {
  return (RUN_VIEWS as readonly string[]).includes(part);
}

export function parseHash(hash: string): Route {
  const path = hash.replace(/^#/, "") || "/";
  const parts = path.split("/").filter((part) => part !== "");
  let ids: string[];
  try {
    ids = parts.map((part) => decodeURIComponent(part));
  } catch {
    return { name: "not_found", path };
  }
  const [top, id, view, target, ...rest] = ids;
  if (top === undefined) {
    return { name: "plants" };
  }
  if (top === "plants" && rest.length === 0 && target === undefined) {
    if (id === undefined) return { name: "plants" };
    if (view === undefined) return { name: "plant", plantId: id };
    if (view === "sections") return { name: "sections", plantId: id };
  }
  if (top === "runs" && rest.length === 0) {
    if (id === undefined) return { name: "runs" };
    if (view === "items" && target !== undefined) {
      return { name: "item", runId: id, targetId: target };
    }
    if (view !== undefined && target === undefined && isRunView(view)) {
      return { name: view, runId: id };
    }
  }
  return { name: "not_found", path };
}
