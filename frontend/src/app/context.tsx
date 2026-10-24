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

type App = {
  client: ApiClient;
  /** the record the drawer shows, or null when it is closed */
  recordId: string | null;
  openRecord: (id: string) => void;
  closeRecord: () => void;
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
  const openRecord = useCallback((id: string) => setRecordId(id), []);
  const closeRecord = useCallback(() => setRecordId(null), []);
  const value = useMemo(
    () => ({ client, recordId, openRecord, closeRecord }),
    [client, recordId, openRecord, closeRecord],
  );
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): App {
  const app = useContext(AppContext);
  if (app === null) throw new Error("useApp needs an AppProvider");
  return app;
}
