// Every run-related screen says what it shows: live, recorded (with its date and cost), or mock.

import type { RunLabel } from "../api/schema";
import { money } from "../format/number";
import { day } from "../format/time";

export function labelText(label: RunLabel): string {
  switch (label.kind) {
    case "live":
      return "Live run";
    case "recorded":
      return `Recorded run — ${day(label.recorded_at)} — cost ${money(label.cost_usd)}`;
    case "mock":
      return "Mock data — not a real plant";
  }
}

export function LabelBanner({ label }: { label: RunLabel }) {
  return (
    <p role="status" className={`banner banner-${label.kind}`}>
      {labelText(label)}
    </p>
  );
}
