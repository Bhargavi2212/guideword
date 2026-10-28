// Record keys in displayed text become the tag or step name they point to (review plan Q7): the
// raw key stays on hover and in the drawer, and the stored text is never changed. The same rule
// as the benchmark's blind sheets (backend `bench/blind.py`):
//   a finding or question key -> its object and words  (f:m:S-EA-425B:more:pressure:… -> EA-425B more pressure)
//   a step key                -> the step and its word   (proc:P-REB-START-2:early -> P-REB-START-2 early)
//   a chain key               -> its named parts, joined with "and"
//   a fact ID                 -> its object and field    (HV-B-SIN.normal_position -> HV-B-SIN normal position)
// Undoing every substitution gives back the stored text exactly (tested).

export type NamedPart = { text: string; key?: string };
export type Named = { text: string; parts: NamedPart[] };

// a record key: its prefix, then everything up to a space or closing punctuation
const KEY =
  /\b(?:f|m|proc|pair|env|nf|relief|work|dust|eng|ai|ch|hyp|ev|lopa|rec):[^\s,;()[\]]*[^\s,;.()[\]]/g;
// a fact ID: an object ID with a hyphen, a dot, a snake_case field (and nested fields)
const FACT =
  /\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\.[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*\b/g;
// the parts of a finding ID that name nothing: its hash, cause and tier
const NOISE = /^(?:[0-9a-f]{16}|C\d+|super|ultra|lightning|nano)$/;

function words(value: string): string {
  return value.replace(/_/g, " ");
}

function questionName(kind: string, parts: string[]): string {
  const rest = parts.filter((p) => !NOISE.test(p));
  const [first = "", second = ""] = rest;
  if (kind === "m" && first.startsWith("S-")) {
    return [first.slice(2).replace(/~/g, " "), ...rest.slice(1)]
      .map(words)
      .join(" ");
  }
  if (kind === "pair" && second) return `${first} and ${second}`;
  if (kind === "env" && second) return `${first} with ${words(second)}`;
  if (kind === "relief" && first) return `${first} relief`;
  if (kind === "nf" && first) return `${first} no flow`;
  if (kind === "dust" && first) return `${first} dust`;
  return rest.map(words).join(" ") || kind;
}

/** The name a record key or fact ID stands for. */
export function keyName(key: string): string {
  if (key.startsWith("ch:")) {
    return key
      .slice(3)
      .split("+")
      .map((link) => keyName(link))
      .join(" and ");
  }
  FACT.lastIndex = 0;
  const fact = new RegExp(`^${FACT.source}$`).test(key);
  if (fact) {
    const dot = key.indexOf(".");
    return `${key.slice(0, dot)} ${words(key.slice(dot + 1).replace(/\./g, " "))}`;
  }
  const parts = key.split(":");
  const kind = parts[0] ?? "";
  if (kind === "f" && parts.length > 1) {
    return questionName(parts[1] ?? "", parts.slice(2));
  }
  return questionName(kind, parts.slice(1));
}

type Match = { start: number; end: number; key: string };

/** The text with its keys named, each named span keeping the key it replaced. */
export function nameKeys(text: string): Named {
  const found: Match[] = [];
  for (const pattern of [KEY, FACT]) {
    for (const m of text.matchAll(pattern)) {
      const start = m.index;
      found.push({ start, end: start + m[0].length, key: m[0] });
    }
  }
  found.sort((a, b) => a.start - b.start || b.end - a.end);
  const parts: NamedPart[] = [];
  let at = 0;
  for (const m of found) {
    if (m.start < at) continue; // inside a key already named
    if (m.start > at) parts.push({ text: text.slice(at, m.start) });
    parts.push({ text: keyName(m.key), key: m.key });
    at = m.end;
  }
  if (at < text.length) parts.push({ text: text.slice(at) });
  return { text: parts.map((p) => p.text).join(""), parts };
}

/** The stored text: every substitution reversed. */
export function undoNames(named: Named): string {
  return named.parts.map((p) => p.key ?? p.text).join("");
}

// a connector handle: `L<n>` (a line sent in the chain-finder's prompt) or `P<n>` (a fact)
const HANDLE = /\b[LP]\d+\b/g;

/** The chain-finder's own handles left in these texts once their keys are named, each once,
 * in order. They meant something only inside that one prompt, so nothing here can name them
 * (decisions row 251); the card flags them instead. */
export function unresolvedHandles(texts: readonly string[]): string[] {
  const found = texts.flatMap((t) => nameKeys(t).text.match(HANDLE) ?? []);
  return found.filter((h, n) => found.indexOf(h) === n);
}

/** The flag Bhargavi wrote for them (2026-10-27), with this card's own numbers. */
export function handleFlag(handles: readonly string[]): string | null {
  if (handles.length === 0) return null;
  return `Line and step numbers (${handles.join(", ")}) from the chain-finder’s prompt; not resolved to plant tags in this development run.`;
}
