// A fake `fetch` for tests: each request path maps to a status and a JSON body (usually a
// contract fixture). A path with no entry answers 404 the way the API does.

export type FakeResponse = { status?: number; body: unknown };
export type FakeCall = { method: string; path: string; body: unknown };

export function fakeFetch(
  routes: Record<string, FakeResponse | (() => FakeResponse)>,
) {
  const calls: FakeCall[] = [];
  const impl = async (
    input: RequestInfo | URL,
    init?: RequestInit,
  ): Promise<Response> => {
    const url = typeof input === "string" ? input : input.toString();
    const path = url.replace(/^https?:\/\/[^/]+/, "");
    const method = init?.method ?? "GET";
    const body =
      typeof init?.body === "string"
        ? (JSON.parse(init.body) as unknown)
        : null;
    calls.push({ method, path, body });
    const entry = routes[`${method} ${path}`] ?? routes[path];
    const answer =
      typeof entry === "function"
        ? entry()
        : (entry ?? {
            status: 404,
            body: { detail: `no route ${path}`, phase: null },
          });
    return new Response(JSON.stringify(answer.body), {
      status: answer.status ?? 200,
      headers: { "content-type": "application/json" },
    });
  };
  return { impl: impl as typeof fetch, calls };
}

/** A `fetch` whose every request fails as a dropped connection does. */
export function offlineFetch(): typeof fetch {
  return (async () => {
    throw new TypeError("Failed to fetch");
  }) as typeof fetch;
}
