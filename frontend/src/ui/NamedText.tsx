// Text with its record keys shown as the names they stand for (review plan Q7). Each named span
// is traced to its key: the raw key is on hover and one click opens it in the drawer; the rest
// of the text is traced to the record it came from.

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
  if (named.parts.every((p) => p.key === undefined)) {
    return <Traced id={traceId}>{text}</Traced>;
  }
  return (
    <>
      {named.parts.map((part, n) =>
        part.key === undefined ? (
          <Traced key={n} id={traceId}>
            {part.text}
          </Traced>
        ) : (
          <Traced key={n} id={part.key}>
            {part.text}
          </Traced>
        ),
      )}
    </>
  );
}
