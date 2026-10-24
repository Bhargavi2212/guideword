// What a card must show the engineer, as code wrote it: every flag verbatim, in order. With a
// `traceId`, each flag opens the record it was written about (P5-6).

import { Traced } from "./Traced";

export function Flags({
  flags,
  traceId,
}: {
  flags: readonly string[];
  traceId?: string;
}) {
  if (flags.length === 0) return null;
  return (
    <ul className="flags">
      {flags.map((flag) => (
        <li key={flag}>
          {traceId === undefined ? flag : <Traced id={traceId}>{flag}</Traced>}
        </li>
      ))}
    </ul>
  );
}
