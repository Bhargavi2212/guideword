// Screen 4 — the shortlist (spec 5.1): the three tiers in the server's order, one card per line.

import { useRef, type KeyboardEvent } from "react";

import { errorMessage } from "../api/client";
import { useFactValues, useResource } from "../api/hooks";
import type { DemoResponse, Shortlist as ShortlistData } from "../api/schema";
import { bannerFor, pickerRuns, startTarget } from "../app/landing";
import { buildHash } from "../app/router";
import { groupByTier } from "../model/shortlist";
import { ExportLinks } from "../ui/ExportLinks";
import { ShortlistCard } from "./ShortlistCard";

export function Shortlist({ runId }: { runId: string }) {
  const shortlist = useResource<ShortlistData>(
    `/runs/${encodeURIComponent(runId)}/shortlist`,
  );
  const list = useRef<HTMLDivElement>(null);
  // on the deployed site, the demo moment's card is marked "start here" (deploy plan D3)
  const demo = useResource<DemoResponse>("/demo");
  const start = startTarget(demo.data, runId);
  const factValues = useFactValues(runId);
  const banner = bannerFor(demo.data, runId);
  const offered = pickerRuns(demo.data);

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
      <ExportLinks runId={runId} />
      {offered.length > 1 && offered.some((r) => r.run_id === runId) ? (
        <label className="plant-picker">
          Plant
          <select
            value={runId}
            onChange={(e) => {
              window.location.hash = buildHash({
                name: "shortlist",
                runId: e.target.value,
              });
            }}
          >
            {offered.map((r) => (
              <option key={r.run_id} value={r.run_id}>
                {r.plant_id}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      {banner !== null && shortlist.data.label.kind === "recorded" ? (
        <p className="demo-banner" role="note">
          <BannerText
            banner={banner}
            startRank={
              shortlist.data.items.find((i) => i.target_id === start)?.rank ??
              null
            }
            onLine={() => {
              // the page opens at the top; the banner's line number goes to the card (F6)
              Array.from(
                list.current?.querySelectorAll<HTMLElement>("article") ?? [],
              )
                .find((a) => a.dataset.targetId === start)
                ?.scrollIntoView({ block: "center" });
            }}
          />
        </p>
      ) : null}
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
                severityClasses={shortlist.data?.severity_classes ?? []}
                factValues={factValues}
                start={item.target_id === start}
                onKeyDown={move}
              />
            ))}
          </section>
        ))}
      </div>
    </section>
  );
}

/** The banner as written, with its "Line #N" a link to the start card when N is that card's
 * rank; otherwise the banner as plain text. */
function BannerText({
  banner,
  startRank,
  onLine,
}: {
  banner: string;
  startRank: number | null;
  onLine: () => void;
}) {
  const line = startRank === null ? null : `Line #${String(startRank)}`;
  const at = line === null ? -1 : banner.indexOf(line);
  // "Line #2" must not match the start of "Line #20"
  const whole = at >= 0 && !/\d/.test(banner.charAt(at + (line?.length ?? 0)));
  if (line === null || !whole) return <>{banner}</>;
  return (
    <>
      {banner.slice(0, at)}
      <button type="button" className="link-button" onClick={onLine}>
        {line}
      </button>
      {banner.slice(at + line.length)}
    </>
  );
}
