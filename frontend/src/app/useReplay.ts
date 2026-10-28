// The replay player (P5-4): shows a finished run's events one by one, each after its wait.
// Changing the speed changes the waits still to come, never the order; "jump to end" shows
// every event at once. Events that arrive later (the next page) join the queue.

import { useCallback, useEffect, useState } from "react";

export type Replay = { shown: number; jumpToEnd: () => void };

/** `delays` null is not a replay: nothing is scheduled. */
export function useReplay(delays: readonly number[] | null): Replay {
  const [shown, setShown] = useState(0);
  const [atEnd, setAtEnd] = useState(false);
  const total = delays?.length ?? 0;
  useEffect(() => {
    if (delays === null || atEnd || shown >= delays.length) return;
    const timer = window.setTimeout(
      () => setShown((n) => n + 1),
      delays[shown] ?? 0,
    );
    return () => window.clearTimeout(timer);
  }, [delays, shown, atEnd]);
  const jumpToEnd = useCallback(() => setAtEnd(true), []);
  return { shown: atEnd ? total : Math.min(shown, total), jumpToEnd };
}
