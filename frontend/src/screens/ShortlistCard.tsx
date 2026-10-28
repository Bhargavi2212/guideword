// One shortlist line as a card (spec 5.1). Every number, ID and claim on it is traced (P5-6).
// Two layers, both visible (review plan R3): a plain title on top, one fixed template per line
// kind; below it the technical layer: the tags, the LOPA line, the severity code with the
// table's definition, and the gap as "N× over the risk limit" (Q10). Record keys in the text
// show as names, the raw key on hover and in the drawer (Q7). Evidence is shown as written.

import type { KeyboardEvent } from "react";

import type { Shortlist, ShortlistItem } from "../api/schema";
import { buildHash } from "../app/router";
import {
  calculationOf,
  isSkipped,
  shownFlag,
  skippedLine,
} from "../model/evidence";
import { keyName } from "../model/names";
import {
  chainHandleFlag,
  leadText,
  severityOf,
  shownEvidence,
} from "../model/shortlist";
import { gapWords } from "../model/technical";
import { lineTitle } from "../model/titles";
import { ChainFlow } from "../ui/ChainFlow";
import { Chip } from "../ui/Chip";
import { Flags } from "../ui/Flags";
import { LopaBar } from "../ui/LopaBar";
import { NamedText } from "../ui/NamedText";
import { TechnicalLayer } from "../ui/TechnicalLayer";
import { Traced } from "../ui/Traced";

type Props = {
  runId: string;
  item: ShortlistItem;
  // the reference table the severity codes are read against (contract v1.11)
  severityClasses?: Shortlist["severity_classes"];
  // the plant's facts by ID, for the chain flow's stored values (review plan R4)
  factValues?: Record<string, unknown>;
  // each finding's cause by ID, as the worksheet names it (F6)
  causes?: Record<string, string>;
  // the demo moment: the line the landing marks "start here" (deploy plan D3)
  start?: boolean;
  onKeyDown: (event: KeyboardEvent<HTMLAnchorElement>) => void;
};

export function ShortlistCard({
  runId,
  item,
  severityClasses = [],
  factValues = {},
  causes = {},
  start = false,
  onKeyDown,
}: Props) {
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
        {start ? <span className="badge badge-start">start here</span> : null}
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
      <h4 className="card-title">
        <Traced id={item.target_id}>{lineTitle(item)}</Traced>
      </h4>
      <p className="card-lead">
        <NamedText text={leadText(item)} traceId={item.target_id} />
      </p>
      <TechnicalLayer item={item} severityClasses={severityClasses} />
      {item.chain ? (
        <ChainFlow
          links={item.chain.links}
          factValues={factValues}
          evidence={item.evidence ?? []}
          causes={causes}
        />
      ) : null}
      {item.lopa ? <LopaBar lopa={item.lopa} /> : null}
      <p className="card-gap">
        {item.lopa ? (
          <Traced id={item.lopa.id}>{gapWords(item)}</Traced>
        ) : (
          gapWords(item)
        )}
      </p>
      {evidence.length > 0 ? (
        <ul className="card-evidence">
          {evidence.map((e) => (
            <li key={e.id}>
              <Chip kind="verdict" value={e.verdict} />{" "}
              {calculationOf(e) !== null ? (
                <span className="card-calc">
                  <Traced id={e.id}>
                    {`calculation on ${calculationOf(e)?.equipment_id ?? ""}`}
                    {(e.via_ids ?? []).length > 0
                      ? ` · via ${(e.via_ids ?? []).map(keyName).join(", ")}`
                      : ""}
                  </Traced>
                  {": "}
                </span>
              ) : null}
              <Traced id={e.id}>
                {isSkipped(e) ? skippedLine(e) : e.summary}
              </Traced>
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
      <Flags
        flags={[
          ...(item.flags ?? []).map(shownFlag),
          ...[chainHandleFlag(item)].filter((f): f is string => f !== null),
        ]}
        traceId={item.target_id}
      />
    </article>
  );
}
