// Typed access to the contract fixtures in tests. A JSON import types every string as `string`,
// so a fixture is checked against its response type with string enums widened: a fixture whose
// fields or shapes drift from the contract fails `typecheck`. The enum values themselves are
// checked by the backend's contract tests, which validate every fixture against its model.

type Widen<T> = T extends string
  ? string
  : T extends boolean
    ? boolean
    : T extends readonly (infer U)[]
      ? Widen<U>[]
      : T extends object
        ? { [K in keyof T]: Widen<T[K]> }
        : T;

export function fixture<T>(json: Widen<T>): T {
  return json as T;
}
