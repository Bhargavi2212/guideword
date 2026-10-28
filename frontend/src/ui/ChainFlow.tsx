// A chain as a flow (review plan R4): its links in stored order, boxes joined by arrows. Each
// box shows its tag or step name and the fact's stored value; a valve stored closed is marked
// "closed" in red; a calculation's result sits in the box on its equipment. Each box opens its
// record (a finding, or a plant fact) in the drawer.

import type { Evidence } from "../api/schema";
import { chainFlow } from "../model/visuals";
import { Chip } from "./Chip";
import { Traced } from "./Traced";

export function ChainFlow({
  links,
  factValues,
  evidence,
  label = "Chain flow",
}: {
  links: readonly string[];
  factValues: Record<string, unknown>;
  evidence: readonly Evidence[];
  label?: string;
}) {
  const boxes = chainFlow(links, factValues, evidence);
  return (
    <ol className="chain-flow" aria-label={label}>
      {boxes.map((box) => (
        <li
          key={box.id}
          className={`flow-box flow-${box.kind}${box.closed ? " flow-closed" : ""}`}
          data-link={box.id}
        >
          <Traced id={box.id}>
            <span className="flow-name">{box.name}</span>
            {box.value !== null ? (
              <span className="flow-value">{box.value}</span>
            ) : null}
          </Traced>
          {box.calculations.map((c) => (
            <span key={c.id} className="flow-calc">
              <Chip kind="verdict" value={c.verdict} />{" "}
              <Traced id={c.id}>{c.summary}</Traced>
            </span>
          ))}
        </li>
      ))}
    </ol>
  );
}
