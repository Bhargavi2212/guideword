// The engineer's display name, sent as an override's `by` (P5-7). Kept in localStorage as a
// per-viewer convenience; storage that is blocked or full is never an error.

export const ENGINEER_KEY = "guideword.engineer";

/** The browser's localStorage, or null where the accessor itself throws. */
export function browserStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function loadEngineer(storage: Storage | null): string {
  try {
    return storage?.getItem(ENGINEER_KEY) ?? "";
  } catch {
    return "";
  }
}

export function saveEngineer(storage: Storage | null, name: string): void {
  try {
    storage?.setItem(ENGINEER_KEY, name);
  } catch {
    // kept in memory for this session only
  }
}
