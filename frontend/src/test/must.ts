/** A value a test needs; fails the test, by name, when it is missing. */
export function must<T>(value: T | null | undefined, what = "value"): T {
  if (value === null || value === undefined)
    throw new Error(`test needs ${what}`);
  return value;
}
