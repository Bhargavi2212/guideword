// Screen 4 — the shortlist (spec 5.1): the three tiers in the server's order, one card per line.

import { useRef, type KeyboardEvent } from "react";

import { errorMessage } from "../api/client";
import { useResource } from "../api/hooks";
import type { Shortlist as ShortlistData } from "../api/schema";
import { groupByTier } from "../model/shortlist";
import { ShortlistCard } from "./ShortlistCard";

export function Shortlist({ runId }: { runId: string }) {
  const shortlist = useResource<ShortlistData>(
    `/runs/${encodeURIComponent(runId)}/shortlist`,
  );
  const list = useRef<HTMLDivElement>(null);

  // the arrow keys move between the cards' links, in the order shown
  function move(event: KeyboardEvent<HTMLAnchorElement>): void {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    const links = Array.from(
      list.current?.querySelectorAll<HTMLAnchorElement>("a.card-open") ?? [],
    );
    const at = links.indexOf(event.currentTarget);
    const next = links[at + (event.key === "ArrowDown" ? 1 : -1)];
    if (next !== undefined) {
      event.preventDefault();
      next.focus();
    }
  }

  if (shortlist.error !== null) {
    return (
      <section>
        <h2>Shortlist</h2>
        <p role="alert">{errorMessage(shortlist.error)}</p>
        {shortlist.error.retriable ? (
          <button type="button" onClick={shortlist.reload}>
            Retry
          </button>
        ) : null}
      </section>
    );
  }
  if (shortlist.data === null) {
    return (
      <section>
        <h2>Shortlist</h2>
        <p>Loading…</p>
      </section>
    );
  }
  return (
    <section>
      <h2>Shortlist</h2>
      <div ref={list} className="tiers">
        {groupByTier(shortlist.data.items).map((group) => (
          <section key={group.tier} className="tier">
            <h3>{group.title}</h3>
            {group.items.length === 0 ? (
              <p className="placeholder">none</p>
            ) : null}
            {group.items.map((item) => (
              <ShortlistCard
                key={item.target_id}
                runId={runId}
                item={item}
                onKeyDown={move}
              />
            ))}
          </section>
        ))}
      </div>
    </section>
  );
}
