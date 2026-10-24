// A LOPA record as table rows (spec 5.2): Ultra's say and code's credit kept apart, side by side.

import type { LopaRecord } from "../api/schema";

export type LayerRow = {
  layerId: string;
  layerType: string | null;
  // Ultra's argument: whether the layer applies here, and why (null: it was not argued)
  applies: boolean | null;
  argument: string | null;
  // code's decision: the credit, the PFD it credits, and code's reason
  credited: boolean;
  pfd: number | null;
  reason: string;
};

export function layerRows(lopa: LopaRecord): LayerRow[] {
  return (lopa.layers ?? []).map((layer) => ({
    layerId: layer.layer_id,
    layerType: layer.layer_type ?? null,
    applies: layer.applies ?? null,
    argument: layer.argument ?? null,
    credited: layer.credited,
    pfd: layer.pfd ?? null,
    reason: layer.reason,
  }));
}

/** Ultra's yes or no, in words. */
export function appliesText(applies: boolean | null): string {
  if (applies === null) return "not argued";
  return applies ? "applies" : "does not apply";
}
