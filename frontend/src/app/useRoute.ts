// The current route, from the location hash; it follows every hashchange.

import { useSyncExternalStore } from "react";

import { parseHash, type Route } from "./router";

function subscribe(onChange: () => void): () => void {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}

function hash(): string {
  return window.location.hash;
}

export function useRoute(): Route {
  const current = useSyncExternalStore(subscribe, hash, () => "");
  return parseHash(current);
}
