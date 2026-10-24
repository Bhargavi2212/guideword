// Every number, ID and claim on screen opens the record it came from (P5-6, CLAUDE.md section 3).

import type { ReactNode } from "react";

import { useApp } from "../app/context";

export function Traced({ id, children }: { id: string; children: ReactNode }) {
  const { openRecord } = useApp();
  return (
    <button
      type="button"
      className="traced"
      data-record-id={id}
      title={id}
      onClick={() => openRecord(id)}
    >
      {children}
    </button>
  );
}
