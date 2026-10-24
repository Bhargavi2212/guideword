// The most a run can spend (C7, Q10): its spend cap plus its post-analysis cap.

import { money } from "../format/number";

export function CostLine({
  spendCapUsd,
  postCapUsd,
}: {
  spendCapUsd: number;
  postCapUsd: number;
}) {
  return (
    <p className="cost-line">
      {`Up to ${money(spendCapUsd + postCapUsd)}: spend cap ${money(spendCapUsd)} + post cap ${money(postCapUsd)}`}
    </p>
  );
}
