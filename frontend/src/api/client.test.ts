import { describe, expect, it } from "vitest";

import runDetail from "../../../contract/fixtures/run_detail.json";
import { fakeFetch, offlineFetch } from "../test/fakeFetch";
import { fixture } from "../test/fixtures";
import {
  ApiClient,
  ApiError,
  errorMessage,
  overrideBlockedReason,
} from "./client";
import type { RunDetail, RunLabel } from "./schema";

const detail = fixture<RunDetail>(runDetail);
const RUN = detail.run.id;

describe("ApiClient", () => {
  it("reads a typed response", async () => {
    const fake = fakeFetch({
      [`/runs/${encodeURIComponent(RUN)}`]: { body: detail },
    });
    const client = new ApiClient("", fake.impl);
    const got = await client.get<RunDetail>(`/runs/${encodeURIComponent(RUN)}`);
    expect(got.run.id).toBe(RUN);
    expect(fake.calls).toEqual([
      { method: "GET", path: `/runs/${encodeURIComponent(RUN)}`, body: null },
    ]);
  });

  it("posts JSON", async () => {
    const fake = fakeFetch({ "POST /runs": { body: { ok: true } } });
    await new ApiClient("", fake.impl).post("/runs", { plant_id: "p" });
    expect(fake.calls[0]).toEqual({
      method: "POST",
      path: "/runs",
      body: { plant_id: "p" },
    });
  });

  it.each([
    [
      501,
      { detail: "not implemented until phase 7", phase: 7 },
      "Not built until Phase 7",
    ],
    [
      403,
      { detail: "recorded run is read-only", phase: null },
      "This run is recorded and read-only",
    ],
    [404, { detail: "no run run:x", phase: null }, "Not found: no run run:x"],
    [
      409,
      { detail: "cap reached; raise spend_cap_usd to continue", phase: null },
      "cap reached; raise spend_cap_usd to continue",
    ],
    [500, { detail: "boom", phase: null }, "The server failed (500): boom"],
  ])("maps %i to its message", async (status, body, message) => {
    const fake = fakeFetch({ "/x": { status, body } });
    const error = await new ApiClient("", fake.impl)
      .get("/x")
      .catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(status);
    expect(errorMessage(error as ApiError)).toBe(message);
  });

  it("names the phase a 501 waits for", async () => {
    const fake = fakeFetch({
      "/demo": { status: 501, body: { detail: "x", phase: 7 } },
    });
    const error = (await new ApiClient("", fake.impl)
      .get("/demo")
      .catch((e: unknown) => e)) as ApiError;
    expect(error.phase).toBe(7);
  });

  it("turns a dropped connection into a network error the page can retry", async () => {
    const error = (await new ApiClient("", offlineFetch())
      .get("/runs")
      .catch((e: unknown) => e)) as ApiError;
    expect(error.status).toBe(0);
    expect(error.retriable).toBe(true);
    expect(errorMessage(error)).toBe("Cannot reach the server — retry");
  });

  it("prefixes the base URL", async () => {
    const fake = fakeFetch({ "/runs": { body: { runs: [] } } });
    await new ApiClient("http://api.local", fake.impl).get("/runs");
    expect(fake.calls[0]?.path).toBe("/runs");
  });
});

describe("overrides (P5-7)", () => {
  const label = (kind: RunLabel["kind"]): RunLabel => ({
    kind,
    recorded_at: null,
    cost_usd: null,
  });

  it.each([
    ["recorded", "This run is recorded and read-only"],
    ["mock", "This is mock data: nothing is saved"],
  ] as const)("are refused on a %s run with the reason", (kind, reason) => {
    expect(overrideBlockedReason(label(kind))).toBe(reason);
  });

  it("are allowed on a live run", () => {
    expect(overrideBlockedReason(label("live"))).toBeNull();
  });

  it("are never sent for a recorded or mock run", async () => {
    const fake = fakeFetch({
      [`POST /runs/${encodeURIComponent(RUN)}/overrides`]: { body: {} },
    });
    const client = new ApiClient("", fake.impl);
    for (const kind of ["recorded", "mock"] as const) {
      const error = await client
        .postOverride(RUN, label(kind), {
          target_id: "f:x",
          action: "accept",
          new_value: null,
          reason: "r",
          by: "B",
        })
        .catch((e: unknown) => e);
      expect(error).toBeInstanceOf(ApiError);
    }
    expect(fake.calls).toEqual([]);
  });
});
