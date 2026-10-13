# Feedback log: Token Factory, AI Cloud and NVIDIA models

Kept from day 1 for the hackathon's feedback submission. One row per friction point. Add a row the day it happens.

| Date | Tool | What happened | What would help |
|---|---|---|---|
| Kill tests (before 2026-10-12) | Token Factory API | Calls made with the wrong key returned a bare 401, with nothing to show which key or project was wrong. | An error body naming the key's project (masked) or saying "key not found" vs "key lacks access to this model". |
| Kill tests (before 2026-10-12) | Nemotron models via Token Factory | Answers were cut off at the token limit, often mid-JSON, after long reasoning used up the budget. | A documented way to cap reasoning separately from the answer, and clear guidance on `finish_reason: length` with reasoning on. |
| Kill tests (before 2026-10-12) | Nemotron outputs | Unicode hyphens and dashes (and non-breaking spaces) in answers broke plain keyword scoring. | An option for ASCII-normalised output, or a note in the docs that outputs may contain typographic Unicode. |
| Kill tests (before 2026-10-12) | Nemotron 3 Nano | Very slow on some prompts because of very long reasoning before the answer. | A reasoning-off switch documented per model, and per-model guidance on expected latency with reasoning on. |
| Kill tests (before 2026-10-12) | Token Factory catalog | Models were deprecated from the catalog with no automatic rerouting; calls by the old ID simply failed. | Deprecation dates in the model list, and an alias or redirect to the successor model for a grace period. |
| 2026-10-13 | Nemotron 3.5 Lightning, Nemotron 3 Ultra (smoke T3, T4) | With reasoning on, a strict `json_schema` (Lightning) or `json_object` (Ultra) request returned plain-text reasoning ("Here's a thinking process: …") in `content` instead of JSON, until the token limit. No `<think>` tags and no `reasoning_content`, so the reasoning cannot be separated from the answer. | Enforce the schema on `content` whenever `json_schema` strict is requested, or always route reasoning to `reasoning_content`; document which models honour strict schemas with reasoning on. |
| 2026-10-13 | Nemotron 3 Nano 30B (smoke T2) | "Reply with the word OK" billed 166 output tokens for `content` " \n OK", with no reasoning returned anywhere. | Return the reasoning (or report reasoning tokens separately in `usage`) so billed tokens can be accounted for. |
| 2026-10-13 | Token Factory, `reasoning_budget` (smoke T6) | Accepted on Ultra and Super with no visible effect on a short prompt, and no documentation of what it limits. | Document `reasoning_budget` per model, and report reasoning tokens in `usage`. |
| 2026-10-13 | Token Factory model list (smoke T1) | Helpful: every entry has a `shutdown_date` field (empty today), so retirements can be detected in code. | Fill it in ahead of retirements, and add per-model prices and context length to the same list. |
