// Short names for the generated contract types (src/api/types.ts, from contract/openapi.json).
// Nothing here is written by hand: each name is an alias of one schema.

import type { components } from "./types";

type S = components["schemas"];

export type Budget = S["Budget"];
export type Chain = S["Chain"];
export type Coverage = S["Coverage"];
export type DemoResponse = S["DemoResponse"];
export type ErrorBody = S["ErrorBody"];
export type EventsPage = S["EventsPage"];
export type Evidence = S["Evidence"];
export type Finding = S["Finding"];
export type Hypothesis = S["Hypothesis"];
export type LopaRecord = S["LopaRecord"];
export type ModelCall = S["ModelCall"];
export type OverrideRequest = S["OverrideRequest"];
export type OverrideResult = S["OverrideResult"];
export type PlantDetail = S["PlantDetail"];
export type PlantFact = S["PlantFact"];
export type PlantList = S["PlantList"];
export type PlantSummary = S["PlantSummary"];
export type Recommendation = S["Recommendation"];
export type RecordDetail = S["RecordDetail"];
export type Run = S["Run"];
export type RunDetail = S["RunDetail"];
export type RunLabel = S["RunLabel"];
export type RunList = S["RunList"];
export type Shortlist = S["Shortlist"];
export type ShortlistItem = S["ShortlistItem"];
export type ShortlistEvidence = S["ShortlistEvidence"];
export type ToolCall = S["ToolCall"];
export type UseBudget = S["UseBudget"];
