// A small labelled state (P5-10): severity S1–S5, tier, verdict, origin or status. The state is in
// the text and the shape, never in colour alone.

export type ChipKind = "severity" | "tier" | "verdict" | "origin" | "status";

export function Chip({ kind, value }: { kind: ChipKind; value: string }) {
  return (
    <span className={`chip chip-${kind} chip-${kind}-${value}`}>{value}</span>
  );
}
