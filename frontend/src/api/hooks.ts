// Data fetching lives in hooks, never in components (CLAUDE.md section 9).

import { useCallback, useEffect, useState } from "react";

import { useApp } from "../app/context";
import { ApiError } from "./client";
import type { PlantDetail, RunDetail, Worksheet } from "./schema";

export type Resource<T> = {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  reload: () => void;
};

/** GET `path` (none while it is null); `reload` asks again. */
export function useResource<T>(path: string | null): Resource<T> {
  const { client } = useApp();
  const [state, setState] = useState<{
    path: string | null;
    data: T | null;
    error: ApiError | null;
  }>({ path: null, data: null, error: null });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (path === null) return;
    let live = true;
    client.get<T>(path).then(
      (data) => {
        if (live) setState({ path, data, error: null });
      },
      (error: unknown) => {
        if (!live) return;
        const failure =
          error instanceof ApiError ? error : new ApiError(0, String(error));
        setState({ path, data: null, error: failure });
      },
    );
    return () => {
      live = false;
    };
  }, [client, path, attempt]);
  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  const current = state.path === path;
  return {
    data: current ? state.data : null,
    error: current ? state.error : null,
    loading:
      path !== null &&
      (!current || (state.data === null && state.error === null)),
    reload,
  };
}

/** `useResource`, asked again every `everyMs` while `active` and the tab is visible. */
export function usePolling<T>(
  path: string | null,
  everyMs: number,
  active: boolean,
): Resource<T> {
  const resource = useResource<T>(path);
  const { reload } = resource;
  useEffect(() => {
    if (!active || path === null) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState !== "hidden") reload();
    }, everyMs);
    return () => window.clearInterval(timer);
  }, [active, everyMs, path, reload]);
  return resource;
}

/** The run's plant facts by ID, so a line shows the values it names (review plan R3, R4); empty
 * until they load. */
export function useFactValues(runId: string): Record<string, unknown> {
  const run = useResource<RunDetail>(`/runs/${encodeURIComponent(runId)}`);
  const plantId = run.data?.run.plant_record_id ?? null;
  const plant = useResource<PlantDetail>(
    plantId === null ? null : `/plants/${encodeURIComponent(plantId)}`,
  );
  return Object.fromEntries(
    (plant.data?.facts ?? []).map((f) => [f.id, f.value]),
  );
}

/** Each finding's cause as the run's worksheet names it (`C14 Wrong material charged … (P-1)`),
 * by finding ID; empty until it loads (F6). */
export function useFindingCauses(runId: string): Record<string, string> {
  const sheet = useResource<Worksheet>(
    `/runs/${encodeURIComponent(runId)}/worksheet`,
  );
  return Object.fromEntries(
    (sheet.data?.rows ?? [])
      .filter((r) => r.row_id.startsWith("f:"))
      .map((r) => [r.row_id, r.causes]),
  );
}
