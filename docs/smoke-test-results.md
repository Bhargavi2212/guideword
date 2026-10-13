# Smoke test results — Phase 0 (spec 0.4)

**Run:** 2026-10-13 12:29 UTC by Bhargavi, `python scripts/smoke_test.py --phase 0 --use development`, on Nebius Token Factory.
**Result:** complete. 40 paid model calls and 1 Tavily search; every call went through `scripts/live_call.py`.
**Spent:** **$0.1277** (phase 0 cap $0.65). Ultra $0.1262 (of which T14 $0.1221), Super $0.0007, Lightning $0.0004, Nano $0.0004.
**Raw responses:** `docs/smoke/<test>-<tier>.json` (checked for keys before saving; no headers), summary in `docs/smoke/summary.json`. Every number below is copied by script from `summary.json`.

## Results

"Reasoning in" is where the script found reasoning text: the `reasoning_content` field, `<think>` tags, or neither. T7 rows combine the tool call and its follow-up (two calls each), so 36 cost rows cover 40 calls.

| Test | Tier | Status | Finish | Reasoning in | Tokens in / out | Cost (USD) | Latency (ms) | Notes |
|---|---|---|---|---|---|---|---|---|
| T1 | ultra | pass | – | – | – | – | – | exact ID; extra fields: shutdown_date |
| T1 | super | pass | – | – | – | – | – | exact ID; extra fields: shutdown_date |
| T1 | lightning | pass | – | – | – | – | – | exact ID; extra fields: shutdown_date |
| T1 | nano | pass | – | – | – | – | – | exact ID; extra fields: shutdown_date |
| T2 | ultra | pass | stop | reasoning_content | 22 / 15 | 0.00007 | 624 |  |
| T2 | super | pass | stop | reasoning_content | 22 / 27 | 0.00003 | 950 |  |
| T2 | lightning | pass | stop | reasoning_content | 22 / 87 | 0.00002 | 872 |  |
| T2 | nano | pass | stop | none | 22 / 166 | 0.00004 | 1046 |  |
| T3 | ultra | pass | stop | reasoning_content | 30 / 77 | 0.00026 | 784 | valid JSON for the schema |
| T3 | super | pass | stop | reasoning_content | 30 / 125 | 0.00012 | 1296 | valid JSON for the schema |
| T3 | lightning | fail | length | none | 30 / 400 | 0.00010 | 5236 | truncated at max_tokens; not parsed |
| T3 | nano | pass | stop | none | 30 / 185 | 0.00005 | 880 | valid JSON for the schema |
| T4 | ultra | fail | length | none | 67 / 400 | 0.00127 | 1782 | truncated at max_tokens; not parsed |
| T4 | super | pass | stop | reasoning_content | 67 / 227 | 0.00022 | 1428 | valid JSON for the schema |
| T4 | lightning | fail | length | none | 67 / 400 | 0.00010 | 5123 | truncated at max_tokens; not parsed |
| T4 | nano | pass | stop | none | 67 / 277 | 0.00007 | 1516 | valid JSON for the schema |
| T5 | ultra | pass | stop | none | 22 / 2 | 0.00003 | 540 | output tokens 2 vs T2 15 |
| T5 | super | pass | stop | none | 22 / 2 | 0.00001 | 344 | output tokens 2 vs T2 27 |
| T5 | lightning | pass | stop | none | 22 / 2 | 0.00000 | 240 | output tokens 2 vs T2 87 |
| T5 | nano | pass | stop | none | 22 / 2 | 0.00000 | 270 | output tokens 2 vs T2 166 |
| T6 | ultra | pass | stop | reasoning_content | 22 / 15 | 0.00007 | 585 | output tokens 15 vs T2 15 |
| T6 | super | pass | stop | reasoning_content | 22 / 27 | 0.00003 | 859 | output tokens 27 vs T2 27 |
| T7 | ultra | pass | stop | reasoning_content | 684 / 108 | 0.00101 | 1451 | tool lookup_unit; arguments valid JSON; follow-up used result: True |
| T7 | super | pass | stop | reasoning_content | 778 / 69 | 0.00030 | 1358 | tool lookup_unit; arguments valid JSON; follow-up used result: True |
| T7 | lightning | pass | stop | none | 872 / 64 | 0.00007 | 1336 | tool lookup_unit; arguments valid JSON; follow-up used result: True |
| T7 | nano | pass | stop | none | 614 / 602 | 0.00018 | 4046 | tool lookup_unit; arguments valid JSON; follow-up used result: True |
| T8 | lightning | pass | length | none | 22 / 32 | 0.00001 | 452 | finish_reason=length detected; not parsed |
| T9-1 | lightning | pass | stop | reasoning_content | 22 / 99 | 0.00003 | 1567 |  |
| T9-2 | lightning | pass | stop | reasoning_content | 22 / 99 | 0.00003 | 1070 |  |
| T9-3 | lightning | pass | stop | reasoning_content | 22 / 89 | 0.00002 | 1227 |  |
| T9-4 | lightning | pass | stop | reasoning_content | 22 / 119 | 0.00003 | 1353 |  |
| T9-5 | lightning | pass | stop | reasoning_content | 22 / 85 | 0.00002 | 1048 |  |
| T10 | tavily | pass | – | – | – | – | 3790 | 3 results; top-level keys: answer, follow_up_questions, images, query, request_id, response_time, results |
| T11 | lightning | pass | stop | none | 30 / 25 | 0.00001 | 807 | valid JSON for the schema |
| T11 | nano | pass | stop | none | 30 / 35 | 0.00001 | 675 | valid JSON for the schema |
| T12-auto | ultra | pass | tool_calls | reasoning_content | 384 / 66 | 0.00058 | 721 | chose lookup_unit; arguments valid JSON |
| T12-required | ultra | pass | tool_calls | reasoning_content | 384 / 60 | 0.00056 | 723 | chose lookup_unit; arguments valid JSON |
| T13-1 | ultra | pass | stop | reasoning_content | 22 / 16 | 0.00007 | 599 |  |
| T13-2 | ultra | pass | stop | reasoning_content | 22 / 44 | 0.00015 | 1045 |  |
| T13-3 | ultra | pass | stop | reasoning_content | 22 / 16 | 0.00007 | 938 |  |
| T14 | ultra | pass | stop | reasoning_content | 122,002 / 25 | 0.12208 | 4867 | accepted; real input tokens 122002; cost $0.1221 |

## What the raw responses show

- **Reasoning text inside `content` with structured output.** The three `length` failures in T3/T4 are not schema failures: the raw `content` of Lightning T3 and T4 starts "Here's a thinking process: …", and Ultra T4 (`json_object`) starts "The user asks: …". The model reasoned in plain text (no `<think>` tags, no `reasoning_content`) until the 400-token limit. So the "Reasoning in: none" on those rows means the reasoning was in `content`, which the script cannot tell apart from an answer. Strict `json_schema` did not constrain Lightning while reasoning was on. With reasoning off (T11), Lightning and Nano both returned valid schema JSON in 25–35 tokens.
- **Nano bills reasoning it does not return.** T2 Nano: 166 output tokens billed, `content` " \n OK", no `reasoning_content`, no `<think>` tags. With reasoning off (T5) it used 2 tokens.
- **Reasoning budget had no visible effect** on a one-word prompt (T6 equals T2 on Ultra and Super). The parameter was accepted; whether it caps long reasoning is untested.
- **T14 used more tokens than estimated.** 350,000 characters of filler were estimated at 100,000 tokens (3.5 characters per token, spec 0.3); Token Factory counted 122,002 (about 2.9 characters per token for this text). The estimate is therefore not an upper bound on input tokens. See the open question below.
- **The model list carries `shutdown_date`** on every entry (empty for all 25 models today), so the gateway can see a retirement coming.

## Decisions (applying `PROJECT.md` §16)

| Item | Decision | Evidence |
|---|---|---|
| Structured output, Ultra | `json_schema` (strict) with reasoning on; not `json_object` | T3 pass (reasoning in `reasoning_content`); T4 reasoned in `content` and truncated |
| Structured output, Super | `json_schema` (strict); `json_object` also works | T3, T4 pass |
| Structured output, Lightning | `json_schema` (strict) **with reasoning off only** | T3/T4 reasoned in `content` and truncated; T11 pass |
| Structured output, Nano | `json_schema` (strict), reasoning off | T3, T4, T11 pass; reasoning is billed but hidden |
| Bulk path (T11) | `json_schema` strict + `chat_template_kwargs.enable_thinking: false` on Lightning (and Nano in the comparison) | T11 pass on both, 25–35 output tokens |
| Ultra tool calling (T12) | **Native tool calling confirmed.** The JSON "next action" fallback is not needed | `auto` and `required` both accepted; valid arguments |
| Turning reasoning off | `extra_body={"chat_template_kwargs": {"enable_thinking": false}}`, accepted by all four | T5: 2 output tokens on every tier |
| Where reasoning appears | Ultra, Super: `reasoning_content`. Lightning: `reasoning_content` on plain calls, but plain text in `content` on structured calls with reasoning on. Nano: not returned (billed) | T2, T3, T4 raw responses |
| Reasoning budget | Not relied on. §16 fallback applies: larger token limits plus length-failure detection (a `length` answer is a failure, never parsed) | T6 no visible effect; T8 and T3/T4 length detection worked |
| Safe concurrency | Lightning 5, Ultra 3 (no 429 or 5xx; latency 1048–1567 ms and 599–1045 ms). Super and Nano were not tested in parallel: start them at 3 | T9, T13 |
| Long input on Ultra (T14) | Accepted at 122,002 input tokens, $0.1221 per call. A connector input of 80,000 tokens (`caps.yaml`) costs about $0.08 per call | T14 |
| Model IDs | All four expected IDs are listed exactly; `config/models.yaml` unchanged | T1 |
| Tavily | Works; 3 results with `answer`, `results` and metadata; no usage info returned | T10 |

## Open question for Bhargavi

- **Cost estimate divisor.** Spec 0.3 sets input tokens = characters ÷ 3.5 and calls the estimate an upper bound. T14 shows real tokens 22% above that for English text. Options: keep 3.5 (caps still hold, since spend is recorded at real cost, but a call can pass the pre-check and cost more than estimated), or change the divisor (for example to 2.5) so the pre-check stays an upper bound. Changing it is a spec change, so it is your call.
