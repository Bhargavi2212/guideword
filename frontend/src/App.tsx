import { useMemo } from "react";

import { ApiClient, defaultClient } from "./api/client";
import { AppProvider } from "./app/context";
import { Screen } from "./app/Screen";
import { Shell } from "./app/Shell";
import { useRoute } from "./app/useRoute";

export default function App({ client }: { client?: ApiClient }) {
  const api = useMemo(() => client ?? defaultClient(), [client]);
  const route = useRoute();
  return (
    <AppProvider client={api}>
      <Shell route={route}>
        <Screen route={route} />
      </Shell>
    </AppProvider>
  );
}
