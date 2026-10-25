import { useEffect, useMemo } from "react";

import { ApiClient, defaultClient } from "./api/client";
import { useResource } from "./api/hooks";
import type { DemoResponse } from "./api/schema";
import { AppProvider } from "./app/context";
import { landingRoute } from "./app/landing";
import { buildHash } from "./app/router";
import { Screen } from "./app/Screen";
import { Shell } from "./app/Shell";
import { useRoute } from "./app/useRoute";

export default function App({ client }: { client?: ApiClient }) {
  const api = useMemo(() => client ?? defaultClient(), [client]);
  const route = useRoute();
  return (
    <AppProvider client={api}>
      <Landing />
      <Shell route={route}>
        <Screen route={route} />
      </Shell>
    </AppProvider>
  );
}

/** On the deployed site, the empty hash opens the demo run (deploy plan D3). */
function Landing() {
  const atRoot = ["", "#", "#/"].includes(window.location.hash);
  const demo = useResource<DemoResponse>(atRoot ? "/demo" : null);
  useEffect(() => {
    const target = landingRoute(window.location.hash, demo.data);
    if (target !== null) window.location.hash = buildHash(target);
  }, [demo.data]);
  return null;
}
