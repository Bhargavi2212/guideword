// Text with its record keys shown as the names they stand for (review plan Q7). The whole text
// is one traced span, so it wraps as a sentence and one click opens the record it came from;
// each named key is an <abbr> whose title is the raw key, shown on hover.

import { nameKeys } from "../model/names";
import { Traced } from "./Traced";

export function NamedText({
  text,
  traceId,
}: {
  text: string;
  traceId: string;
}) {
  const named = nameKeys(text);
  return (
    <Traced id={traceId}>
      {named.parts.map((part, n) =>
        part.key === undefined ? (
          part.text
        ) : (
          <abbr key={n} className="named-key" title={part.key}>
            {part.text}
          </abbr>
        ),
      )}
    </Traced>
  );
}
