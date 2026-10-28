// Screen 5 — the finding detail (spec 5.2): one shortlist line, why each number is what it is,
// and the engineer's overrides. The line comes from the run's shortlist; after an override the
// shortlist is read again, so the gap and the order are always the server's (plan G12).

import { useState } from "react";

import { ApiError, errorMessage, overrideBlockedReason } from "../api/client";
import { useFactValues, useResource } from "../api/hooks";
import type { Shortlist, ShortlistItem } from "../api/schema";
import { useApp } from "../app/context";
import { shownFlag } from "../model/evidence";
import { chainHandleFlag, leadText, severityOf } from "../model/shortlist";
import { findingQuestion, questionTitle } from "../model/titles";
import { lineTitle } from "../model/titles";
import { ChainFlow } from "../ui/ChainFlow";
import { Chip } from "../ui/Chip";
import { Flags } from "../ui/Flags";
import { LopaBar } from "../ui/LopaBar";
import { NamedText } from "../ui/NamedText";
import { TechnicalLayer } from "../ui/TechnicalLayer";
import { Traced } from "../ui/Traced";
import { EvidenceCards } from "./EvidenceCards";
import { LopaTable } from "./LopaTable";
import { RecommendationItem, TargetOverrides, type Send } from "./Overrides";

type Props = { runId: string; targetId: string };

export function Detail({ runId, targetId }: Props) {
  const { client, engineer } = useApp();
  const shortlist = useResource<Shortlist>(
    `/runs/${encodeURIComponent(runId)}/shortlist`,
  );
  const [sendError, setSendError] = useState<string | null>(null);
  // the plant's facts, so a calculation card and the chain flow show the values they used
  // (review plan R3, R4)
  const factValues = useFactValues(runId);
  const item =
    shortlist.data?.items.find((i) => i.target_id === targetId) ?? null;

  if (shortlist.error !== null) {
    return (
      <section>
        <h2>Finding detail</h2>
        <p role="alert">{errorMessage(shortlist.error)}</p>
      </section>
    );
  }
  if (shortlist.data === null) {
    return (
      <section>
        <h2>Finding detail</h2>
        <p>Loading…</p>
      </section>
    );
  }
  if (item === null) {
    return (
      <section>
        <h2>Finding detail</h2>
        <p>{targetId} is not on this run's shortlist.</p>
      </section>
    );
  }

  const label = shortlist.data.label;
  const blocked = overrideBlockedReason(label);
  const reload = shortlist.reload;
  const send: Send = (body) => {
    setSendError(null);
    client.postOverride(runId, label, { ...body, by: engineer }).then(
      () => reload(),
      (error: unknown) =>
        setSendError(
          error instanceof ApiError ? errorMessage(error) : String(error),
        ),
    );
  };
  const credit =
    blocked === null && engineer !== "" && item.lopa
      ? (layerId: string, credited: boolean) => {
          const lopaId = item.lopa?.id;
          if (lopaId === undefined) return;
          send({
            target_id: lopaId,
            action: "change_credit",
            new_value: { layer_id: layerId, credited },
            reason: credited
              ? "engineer asserts the layer is credited"
              : "engineer withdraws credit",
          });
        }
      : null;

  return (
    <article className="detail" data-target-id={item.target_id}>
      <h2>
        <span className="detail-kind">{kindTitle(item)}</span>{" "}
        <Traced id={item.target_id}>#{item.rank}</Traced>{" "}
        <span className="detail-title">{lineTitle(item)}</span>
      </h2>
      <TechnicalLayer
        item={item}
        severityClasses={shortlist.data.severity_classes ?? []}
      />
      <What item={item} factValues={factValues} />
      <Flags
        flags={[
          ...(item.flags ?? []).map(shownFlag),
          ...[chainHandleFlag(item)].filter((f): f is string => f !== null),
        ]}
        traceId={item.target_id}
      />
      {(item.support_finding_ids ?? []).length > 0 ? (
        <section>
          <h3 id="support-title">Supporting findings</h3>
          <ul aria-labelledby="support-title">
            {(item.support_finding_ids ?? []).map((id) => (
              <li key={id}>
                <Traced id={id}>{questionTitle(findingQuestion(id))}</Traced>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {item.lopa ? <LopaBar lopa={item.lopa} /> : null}
      {item.lopa ? (
        <LopaTable
          lopa={item.lopa}
          gapText={item.gap_text ?? null}
          onCredit={credit}
        />
      ) : (
        <p>no LOPA</p>
      )}
      <section>
        <h3>Evidence</h3>
        <EvidenceCards evidence={item.evidence ?? []} factValues={factValues} />
      </section>
      <section>
        <h3>Recommendations</h3>
        {(item.recommendations ?? []).length === 0 ? (
          <p className="placeholder">none</p>
        ) : (
          <ul className="recommendations">
            {(item.recommendations ?? []).map((r) => (
              <RecommendationItem
                key={r.id}
                recommendation={r}
                blocked={blocked}
                engineer={engineer}
                send={send}
              />
            ))}
          </ul>
        )}
      </section>
      <TargetOverrides
        targetId={item.target_id}
        kind={item.target_kind}
        consequence={item.finding?.consequence ?? null}
        blocked={blocked}
        engineer={engineer}
        send={send}
      />
      {sendError !== null ? <p role="alert">{sendError}</p> : null}
    </article>
  );
}

function kindTitle(item: ShortlistItem): string {
  return { finding: "Finding", chain: "Chain", hypothesis: "Hypothesis" }[
    item.target_kind
  ];
}

function What({
  item,
  factValues,
}: {
  item: ShortlistItem;
  factValues: Record<string, unknown>;
}) {
  const severity = severityOf(item);
  return (
    <section className="what">
      {severity !== null ? (
        <p>
          <Traced id={item.target_id}>
            <Chip kind="severity" value={severity} />
          </Traced>
        </p>
      ) : null}
      {item.chain ? <ChainWhat item={item} factValues={factValues} /> : null}
      {item.finding ? <FindingWhat item={item} /> : null}
      {item.hypothesis ? (
        <>
          <p className="description">
            <Traced id={item.hypothesis.id}>{item.hypothesis.mechanism}</Traced>
          </p>
          <p>
            Components:{" "}
            {item.hypothesis.component_ids.map((id) => (
              <span key={id}>
                <Traced id={id}>{id}</Traced>{" "}
              </span>
            ))}
          </p>
          <p>{item.hypothesis.reason}</p>
        </>
      ) : null}
      {!item.chain && !item.finding && !item.hypothesis ? (
        <p>{leadText(item)}</p>
      ) : null}
    </section>
  );
}

function ChainWhat({
  item,
  factValues,
}: {
  item: ShortlistItem;
  factValues: Record<string, unknown>;
}) {
  const chain = item.chain;
  if (!chain) return null;
  return (
    <>
      {/* shown as stored: no cleaning of model text (C2) */}
      <p className="description">
        <NamedText text={chain.description} traceId={chain.id} />
      </p>
      <p className="reason">
        <NamedText text={chain.reason} traceId={chain.id} />
      </p>
      <h3>Links</h3>
      <ChainFlow
        links={chain.links}
        factValues={factValues}
        evidence={item.evidence ?? []}
        label="Links"
      />
    </>
  );
}

function FindingWhat({ item }: { item: ShortlistItem }) {
  const finding = item.finding;
  if (!finding) return null;
  return (
    <dl>
      <dt>Question</dt>
      <dd>
        <Traced id={finding.question_id}>
          {questionTitle(finding.question_id)}
        </Traced>
      </dd>
      <dt>Cause</dt>
      <dd>
        {finding.cause_id}
        {finding.cause_text ? ` — ${finding.cause_text}` : ""}
      </dd>
      <dt>Failing</dt>
      <dd>
        {finding.failing_component_ids.map((id) => (
          <span key={id}>
            <Traced id={id}>{id}</Traced>{" "}
          </span>
        ))}
      </dd>
      <dt>Consequence</dt>
      <dd>
        <NamedText text={finding.consequence} traceId={finding.id} />
      </dd>
      <dt>Safeguards</dt>
      <dd>
        {(finding.safeguard_ids ?? []).length === 0
          ? "none named"
          : (finding.safeguard_ids ?? []).map((id) => (
              <span key={id}>
                <Traced id={id}>{id}</Traced>{" "}
              </span>
            ))}
      </dd>
      <dt>Confidence</dt>
      <dd>{finding.confidence}</dd>
    </dl>
  );
}
