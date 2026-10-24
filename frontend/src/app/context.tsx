// What every screen shares: the API client, and which record the drawer shows (P5-6).

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { ApiClient } from "../api/client";
import { browserStorage, loadEngineer, saveEngineer } from "./engineer";

type App = {
  client: ApiClient;
  /** the record the drawer shows, or null when it is closed */
  recordId: string | null;
  openRecord: (id: string) => void;
  closeRecord: () => void;
  /** the engineer's display name, sent as an override's `by` (P5-7) */
  engineer: string;
  setEngineer: (name: string) => void;
};

const AppContext = createContext<App | null>(null);

export function AppProvider({
  client,
  children,
}: {
  client: ApiClient;
  children: ReactNode;
}) {
  const [recordId, setRecordId] = useState<string | null>(null);
  const [engineer, setName] = useState(() => loadEngineer(browserStorage()));
  const openRecord = useCallback((id: string) => setRecordId(id), []);
  const closeRecord = useCallback(() => setRecordId(null), []);
  const setEngineer = useCallback((name: string) => {
    setName(name);
    saveEngineer(browserStorage(), name);
  }, []);
  const value = useMemo(
    () => ({
      client,
      recordId,
      openRecord,
      closeRecord,
      engineer,
      setEngineer,
    }),
    [client, recordId, openRecord, closeRecord, engineer, setEngineer],
  );
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): App {
  const app = useContext(AppContext);
  if (app === null) throw new Error("useApp needs an AppProvider");
  return app;
}
