// One shortlist line as a card (spec 5.1). Every number, ID and claim on it is traced (P5-6);
// the gap and the evidence are shown as the server wrote them (P5-5).

import type { KeyboardEvent } from "react";

import type { ShortlistItem } from "../api/schema";
import { buildHash } from "../app/router";
import { leadText, severityOf, shownEvidence } from "../model/shortlist";
import { Chip } from "../ui/Chip";
import { Flags } from "../ui/Flags";
import { Traced } from "../ui/Traced";

type Props = {
  runId: string;
  item: ShortlistItem;
  onKeyDown: (event: KeyboardEvent<HTMLAnchorElement>) => void;
};

export function ShortlistCard({ runId, item, onKeyDown }: Props) {
  const severity = severityOf(item);
  const evidence = shownEvidence(item);
  const recommendations = item.recommendations ?? [];
  const firstRecommendation = recommendations[0];
  return (
    <article
      className={`card tier-${item.tier}`}
      data-target-id={item.target_id}
    >
      <header className="card-head">
        <Traced id={item.target_id}>#{item.rank}</Traced>
        <a
          className="card-open"
          href={buildHash({ name: "item", runId, targetId: item.target_id })}
          onKeyDown={onKeyDown}
        >
          Open {item.target_kind}
        </a>
        {item.multi_failure ? (
          <span className="badge">multi-failure</span>
        ) : null}
        {item.unsure ? <span className="badge">unsure</span> : null}
        {severity !== null ? (
          <Traced id={item.target_id}>
            <Chip kind="severity" value={severity} />
          </Traced>
        ) : null}
        {item.tier === "confirmed" &&
        item.hypothesis_id &&
        item.hypothesis_rank ? (
          <Traced id={item.hypothesis_id}>
            hypothesis {item.hypothesis_rank}
          </Traced>
        ) : null}
      </header>
      <p className="card-lead">
        <Traced id={item.target_id}>{leadText(item)}</Traced>
      </p>
      <p className="card-gap">
        {item.gap_text && item.lopa ? (
          <Traced id={item.lopa.id}>{item.gap_text}</Traced>
        ) : item.gap_text ? (
          <Traced id={item.target_id}>{item.gap_text}</Traced>
        ) : (
          "no LOPA"
        )}
      </p>
      {evidence.length > 0 ? (
        <ul className="card-evidence">
          {evidence.map((e) => (
            <li key={e.id}>
              <Chip kind="verdict" value={e.verdict} />{" "}
              <Traced id={e.id}>{e.summary}</Traced>
            </li>
          ))}
        </ul>
      ) : null}
      {firstRecommendation !== undefined ? (
        <p className="card-recs">
          <Traced id={firstRecommendation.id}>
            {recommendations.length === 1
              ? "1 recommendation"
              : `${recommendations.length} recommendations`}
          </Traced>
        </p>
      ) : null}
      <Flags flags={item.flags ?? []} traceId={item.target_id} />
    </article>
  );
}
