// Long IDs shown short; the full ID is always one click away in the drawer (spec 5.0).

const KEEP_START = 22;
const KEEP_END = 12;

export function shortId(id: string, max = KEEP_START + KEEP_END + 1): string {
  if (id.length <= max) return id;
  return `${id.slice(0, KEEP_START)}…${id.slice(-KEEP_END)}`;
}

/** A plant fact is `<object id>.<field>`; every record ID has a `<kind>:` prefix or none. */
export function isFactId(id: string): boolean {
  return !id.includes(":") && id.includes(".");
}
