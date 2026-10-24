// The API client (spec 5.0): typed from the contract only, one error type, and the one place
// that refuses an override on a recorded or mock run before anything is sent (P5-7).

import type {
  ErrorBody,
  OverrideRequest,
  OverrideResult,
  RunLabel,
} from "./schema";

// the status a dropped connection reports
const NETWORK = 0;

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  readonly phase: number | null;

  constructor(status: number, detail: string, phase: number | null = null) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.phase = phase;
  }

  /** A dropped connection or a server failure may pass on a retry; a refusal will not. */
  get retriable(): boolean {
    return this.status === NETWORK || this.status >= 500;
  }
}

/** What the page shows for an error, in the engineer's words. */
export function errorMessage(error: ApiError): string {
  switch (error.status) {
    case NETWORK:
      return "Cannot reach the server — retry";
    case 501:
      return `Not built until Phase ${error.phase ?? "?"}`;
    case 403:
      return "This run is recorded and read-only";
    case 404:
      return `Not found: ${error.detail}`;
    case 409:
      return error.detail;
    default:
      return error.status >= 500
        ? `The server failed (${error.status}): ${error.detail}`
        : error.detail;
  }
}

/** Why no override may be sent for a run with this label, or null when one may (P5-7). */
export function overrideBlockedReason(label: RunLabel): string | null {
  if (label.kind === "recorded") return "This run is recorded and read-only";
  if (label.kind === "mock") return "This is mock data: nothing is saved";
  return null;
}

function isErrorBody(value: unknown): value is ErrorBody {
  return typeof value === "object" && value !== null && "detail" in value;
}

export class ApiClient {
  constructor(
    private readonly base: string,
    private readonly fetchImpl: typeof fetch,
  ) {}

  async get<T>(path: string): Promise<T> {
    return this.request<T>("GET", path);
  }

  async post<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>("POST", path, body);
  }

  async put<T>(path: string, body: unknown): Promise<T> {
    return this.request<T>("PUT", path, body);
  }

  /** An engineer's override; refused here, unsent, on a recorded or mock run. */
  async postOverride(
    runId: string,
    label: RunLabel,
    body: OverrideRequest,
  ): Promise<OverrideResult> {
    const blocked = overrideBlockedReason(label);
    if (blocked !== null) throw new ApiError(403, blocked);
    return this.post<OverrideResult>(
      `/runs/${encodeURIComponent(runId)}/overrides`,
      body,
    );
  }

  private async request<T>(
    method: string,
    path: string,
    body?: unknown,
  ): Promise<T> {
    let response: Response;
    try {
      response = await this.fetchImpl(`${this.base}${path}`, {
        method,
        headers:
          body === undefined
            ? undefined
            : { "content-type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch {
      throw new ApiError(NETWORK, "network error");
    }
    const text = await response.text();
    const parsed: unknown = text === "" ? null : JSON.parse(text);
    if (!response.ok) {
      if (isErrorBody(parsed)) {
        throw new ApiError(
          response.status,
          String(parsed.detail),
          parsed.phase ?? null,
        );
      }
      throw new ApiError(
        response.status,
        response.statusText || "request failed",
      );
    }
    return parsed as T;
  }
}

/** The app's client: same origin by default (the dev proxy, then the deployed site). */
export function defaultClient(): ApiClient {
  const base = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";
  return new ApiClient(base, (...args) => fetch(...args));
}
