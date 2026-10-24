// The engineer's overrides on a line (spec 5.2, P5-7): each needs a reason and the engineer's
// name, is refused (with why) on a recorded or mock run, and reloads the line once stored. The
// server recomputes every number; nothing is recomputed here.

import { useState } from "react";

import type { OverrideRequest, Recommendation } from "../api/schema";

export const SEVERITIES = ["S1", "S2", "S3", "S4", "S5"] as const;

export type Send = (body: Omit<OverrideRequest, "by">) => void;

type TargetProps = {
  targetId: string;
  kind: "finding" | "chain" | "hypothesis";
  consequence: string | null;
  blocked: string | null;
  engineer: string;
  send: Send;
};

/** Accept, reject, change severity; and, on a finding, edit its consequence. */
export function TargetOverrides({
  targetId,
  kind,
  consequence,
  blocked,
  engineer,
  send,
}: TargetProps) {
  const [reason, setReason] = useState("");
  const [severity, setSeverity] = useState("");
  const [severityReason, setSeverityReason] = useState("");
  const [edited, setEdited] = useState(consequence ?? "");
  const off = blocked !== null || engineer === "";
  const ready = !off && reason.trim() !== "";
  if (kind === "hypothesis") return null;
  return (
    <section className="overrides" aria-label="Overrides">
      <h3>Overrides</h3>
      {blocked !== null ? <p className="blocked">{blocked}</p> : null}
      {blocked === null && engineer === "" ? (
        <p className="blocked">
          Enter your name in the header to make an override.
        </p>
      ) : null}
      <label>
        Reason
        <input
          value={reason}
          disabled={off}
          onChange={(e) => setReason(e.target.value)}
        />
      </label>
      <button
        type="button"
        disabled={!ready}
        onClick={() =>
          send({
            target_id: targetId,
            action: "accept",
            new_value: null,
            reason,
          })
        }
      >
        Accept {kind}
      </button>
      <button
        type="button"
        disabled={!ready}
        onClick={() =>
          send({
            target_id: targetId,
            action: "reject",
            new_value: null,
            reason,
          })
        }
      >
        Reject {kind}
      </button>
      {kind === "finding" ? (
        <div>
          <label>
            Consequence
            <textarea
              value={edited}
              disabled={off}
              onChange={(e) => setEdited(e.target.value)}
            />
          </label>
          <button
            type="button"
            disabled={!ready || edited.trim() === "" || edited === consequence}
            onClick={() =>
              send({
                target_id: targetId,
                action: "edit",
                new_value: { consequence: edited },
                reason,
              })
            }
          >
            Edit consequence
          </button>
        </div>
      ) : null}
      <div>
        <label>
          New severity
          <select
            value={severity}
            disabled={off}
            onChange={(e) => setSeverity(e.target.value)}
          >
            <option value="" disabled>
              choose
            </option>
            {SEVERITIES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label>
          Reason for the severity
          <input
            value={severityReason}
            disabled={off}
            onChange={(e) => setSeverityReason(e.target.value)}
          />
        </label>
        <button
          type="button"
          disabled={off || severity === "" || severityReason.trim() === ""}
          onClick={() =>
            send({
              target_id: targetId,
              action: "change_severity",
              new_value: { severity_class: severity },
              reason: severityReason,
            })
          }
        >
          Change severity
        </button>
      </div>
    </section>
  );
}

type RecommendationProps = {
  recommendation: Recommendation;
  blocked: string | null;
  engineer: string;
  send: Send;
};

/** Accept, reject or edit one recommendation's action. */
export function RecommendationItem({
  recommendation,
  blocked,
  engineer,
  send,
}: RecommendationProps) {
  const [reason, setReason] = useState("");
  const [action, setAction] = useState(recommendation.action);
  const off = blocked !== null || engineer === "";
  const ready = !off && reason.trim() !== "";
  const id = recommendation.id;
  return (
    <li data-recommendation-id={id}>
      <p className="action">{recommendation.action}</p>
      <p className="reason">{recommendation.reason}</p>
      <label>
        Reason
        <input
          value={reason}
          disabled={off}
          onChange={(e) => setReason(e.target.value)}
        />
      </label>
      <button
        type="button"
        disabled={!ready}
        onClick={() =>
          send({ target_id: id, action: "accept", new_value: null, reason })
        }
      >
        Accept recommendation
      </button>
      <button
        type="button"
        disabled={!ready}
        onClick={() =>
          send({ target_id: id, action: "reject", new_value: null, reason })
        }
      >
        Reject recommendation
      </button>
      <label>
        Action
        <input
          value={action}
          disabled={off}
          onChange={(e) => setAction(e.target.value)}
        />
      </label>
      <button
        type="button"
        disabled={
          !ready || action.trim() === "" || action === recommendation.action
        }
        onClick={() =>
          send({ target_id: id, action: "edit", new_value: { action }, reason })
        }
      >
        Edit action
      </button>
    </li>
  );
}
