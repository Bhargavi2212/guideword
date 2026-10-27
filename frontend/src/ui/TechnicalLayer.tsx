// The technical layer under a line's plain title (review plan R3), on the card and on the
// detail screen alike: the tags the line names, the LOPA line, the severity code with the
// reference table's definition. Every value is traced to the record it came from.

import type { Shortlist, ShortlistItem } from "../api/schema";
import { lineTags, lopaLine, severityText } from "../model/technical";
import { severityOf } from "../model/shortlist";
import { Traced } from "./Traced";

export function TechnicalLayer({
  item,
  severityClasses,
}: {
  item: ShortlistItem;
  severityClasses: Shortlist["severity_classes"];
}) {
  const tags = lineTags(item);
  const severity = severityOf(item);
  return (
    <div className="card-tech">
      {tags.length > 0 ? (
        <p className="card-tags">
          <span className="tech-label">Tags</span>{" "}
          <Traced id={item.target_id}>{tags.join(", ")}</Traced>
        </p>
      ) : null}
      {item.lopa ? (
        <p className="card-lopa">
          <Traced id={item.lopa.id}>{lopaLine(item.lopa)}</Traced>
        </p>
      ) : null}
      {severity !== null ? (
        <p className="card-severity">
          <Traced id={item.target_id}>
            {severityText(severity, severityClasses)}
          </Traced>
        </p>
      ) : null}
    </div>
  );
}
