# Phase 3 follow-up plan: the demo run's two problems

Status: approved 2026-10-21 (Bhargavi; Q1–Q4 as recommended).

Written 2026-10-21, after the Williams Geismar demo run (`run:4e6842d31fbdee3b`, finished, $0.98) and Bhargavi's review of it the same day. `specs/phase-3.md` and the earlier Phase 3 plans still apply. No code is written until this plan is approved.

**Order (Bhargavi):** plans → her review of the v3 wording → retry the failed questions → re-run from chains → the demo report. There is no full re-run of the demo analysis.

## What the demo run's records show

### Problem 1: no "no credit — inlet valve … closed" on the reboilers' relief paths

- **RV-PATH-EA425B:** where it was a candidate, `lopa_argument/v2` answered "does not apply", saying "the scenario is a tube rupture causing direct release". "Does not apply" is decided before the inlet-valve rule, so code never reached it. A shell-side relief path is normally exactly the protection against a tube rupture, so this is an engineering mistake by the model, not a judgment code should defer to.
- **RV-PATH-EA425A:** on one record Ultra refused it because "its inlet valve HV-A-SOUT is closed". In the plant file HV-A-SOUT is open and `locked: true`. Ultra judged a valve state, which `PROJECT.md` §5 Step 6.2 gives to code ("Ultra argues which safeguards apply and why; code decides credit"), and invented that state too.
- **What did work:** where Ultra said yes, code credited RV-PATH-EA425A at `pfd_if_isolatable` because HV-A-SIN is unmanaged, and refused it on 4 records where the path is itself a failing component.

### Problem 2: 15 failed questions, all on three sections

| Section | Bulk (Lightning) | Hard (Super) |
|---|---|---|
| S-EA-425B (reboiler B) | cut off at the token limit | cut off at the token limit |
| S-L-A-SOUT | a question answered twice | "external is not a valid cause for this question" |
| S-L-QW-B-OUT | answered a question not in the batch | cut off at the token limit |

- Each failed as a whole batch of 5. On the demo run, 15 Lightning calls and 2 Super calls hit `max_tokens` (12,288). Super's normal answers average about 4,500 output tokens.
- **The effect (Bhargavi):** S-EA-425B has no findings of its own. The top two confirmed lines are led by `f:env:C4-HEAVIES:air…`, so on camera the reboiler card would cite a C4-heavies-and-air question as its evidence.

### Also seen (no code change)
- **Severity:** every top-10 line is S3. The severity prompt stays frozen. The video shows the engineer applying `change_severity` S3 → S4 with a reason ("contractors in the unit, multiple fatalities credible"), and the gap moves by 10×. The product already does this (PR 6).
- **The report's location:** the demo report went to `bench/test5/5b/williams_geismar.json`, because `run_case.py` writes every report there (`OUT`). `bench/results.py` and `score_test5.py` read only `case_<letter>.json` there, so nothing scored it, but it doesn't belong in test #5's folder. It moves to `bench/demo/` on the records branch, and item 3 stops future demo reports landing there.

## 1. `lopa_argument/v3` (wording for Bhargavi's review)

- **One general rule**, added to "How to judge" and the answer format: *"Judge only whether the layer acts on this scenario's deviation. Valve positions, isolation and lock state are checked by code, never by you: do not say a layer does not apply because a valve is closed, open, locked or unmanaged, and never state a valve's position."*
- **Nothing specific:** no Williams Geismar or example-2 content, and no relief-specific example. The existing general examples stay as they are.
- Routing moves `lopa_argument` to v3 after review. D, E and G stay on their v1 post prompts until the second grant, and F stays on v2.
- **`docs/decisions.md` records why:** Ultra judged a valve state, and invented one (HV-A-SOUT is locked open in the plant file), against `PROJECT.md`'s rule that code decides credit.
- **Test ($0):** the v3 text contains the rule, no relief example, and no ID from D–H or the demo plant.

## 2. Single-question retry for a failed specialist batch (general robustness)

A batch that is **cut off at the token limit**, or whose answer is invalid because a question was **answered twice** or one was answered **that is not in the batch**, is re-asked **one question at a time**, at the same level, before any of its questions is marked failed. A question whose single call also fails counts as one attempt, as today.

- **Future runs** use it in the analysis (`specialists/run.py`). It is gated by a new hashed run cap, `retry_failed_batch_singly: true` (Q1), so D–G and other existing runs replay unchanged: their stored caps lack the key.
- Other failures (for example "external is not a valid cause") are left as they are. They're the model's answer, not a structural failure. The targeted retry below still covers S-L-A-SOUT, because it asks every failed question alone.

## 3. The targeted extension for the demo run

`extend_run.py <run> --retry-failed --post-cap <usd> --use development --out-dir bench/demo`:

1. **Retry:** each `failed` question of a finished run is asked alone, at hard, to its own specialist, in one step (`retry_failed`). No orchestrator call is made: code dispatches them directly, as the orchestrator's `dispatch_specialist` would. A question answered now becomes `answered` with its findings; one that fails again stays `failed`. The step's summary lists both.
2. **Severity:** it rates only the new findings, as the step already does.
3. **Post steps:** they re-run from `chains`, superseding the old records as `--rerun-from chains` does. The connector input changes, because the new findings add lines, so it is paid.
4. **The report** goes to `bench/demo/williams_geismar.json`.

- **Refused** unless the run is `finished` and has failed questions. The whole-plant pass and the 146 checked questions are untouched, and the hypotheses' tiers and leads are recomputed on read from the new findings.
- **Spend:** the retry and severity spend count against the analysis cap, $0.849 of $1.00 used. The extension raises `spend_cap_usd` by `--retry-cap` (default $0.30). The cap is not hashed into the run ID, so the ID stays.
- **`--out-dir` (Q3):** added to `run_case.py` and `extend_run.py`. Reports for plants under `cases/demo/` default to `bench/demo/`.

### Does any orchestrator call run again?
**No.** The retry is a code step, not the analysis loop, so the 18 orchestrator calls are never re-sent. The only Ultra calls are severity (new findings) and the post steps. The `finish` guard isn't re-entered either: the run finished with every question answered, not credible, or failed (listed).

### Cost of this path (not a full re-run)

| Part | Calls | Typical | Worst case |
|---|---|---|---|
| 15 single-question retries (Super, about 4,000 input tokens each) | 15, plus at most 15 validation retries | $0.05–0.09 | $0.37 (all cut off, twice) |
| Severity for the new findings (about 10 per call) | 2–4 | $0.03–0.07 | $0.07 |
| Post steps from `chains` (connector, chain severity, LOPA, recommendations) | about 10 | $0.12–0.15 | $0.20 |
| **Total** | | **about $0.20–0.30** | **about $0.64** |

Phase 3 has $0.60 left of $2.50, and development $1.38. Two caps keep this inside them: `--retry-cap 0.30` covers the retry and severity, and `--post-cap 0.30` the post steps. Every call is also checked against the Phase 3 cap. At worst the run stops `stopped_cap` with what was done kept, and resumes as before. A full re-run of the analysis would cost about $0.85 more.

## Pull requests, in order

| # | Branch | What |
|---|---|---|
| 0 | `phase-3/records` | the D–G reports and the demo report, moved to `bench/demo/`; a results note. The ledger snapshot `budget/ledger-g3pre.jsonl` and the final demo report are added once the demo re-run is done (Q4). |
| 1 | `phase-3/lopa-argument-v3-prompt` | this plan and `prompts/lopa_argument/v3.md` (not routed). **Bhargavi reviews the wording**, and runs `prompt_leak_check.py` ($0). |
| 2 | `phase-3/retry-failed` | items 2 and 3; routing `lopa_argument: v3`; decisions; a feedback-log entry for the cut-offs |

### Tests first (all $0)
- `test_a_cut_off_batch_is_re_asked_one_question_at_a_time`
- `test_a_batch_answering_a_question_twice_or_one_not_sent_is_re_asked_singly`
- `test_other_invalid_answers_still_fail_the_batch_as_before`
- `test_the_single_retry_is_off_for_runs_whose_caps_lack_the_key` (D–G replay unchanged)
- `test_retry_failed_asks_each_failed_question_alone_and_makes_no_orchestrator_call`
- `test_retry_failed_keeps_the_run_id_and_every_checked_question`
- `test_retry_failed_rates_only_new_findings_then_reruns_from_chains`
- `test_retry_failed_is_refused_for_an_unfinished_run_or_one_with_no_failed_questions`
- `test_a_demo_plant_report_goes_to_bench_demo`
- `test_lopa_argument_v3_leaves_valve_states_to_code` (wording; no relief example; no real IDs)

## Live calls (Bhargavi starts each one)

| Step | Use | Expected |
|---|---|---|
| `prompt_leak_check.py` on v3 | — | $0 |
| `extend_run.py run:4e6842d31fbdee3b --retry-failed --post-cap 0.30 --out-dir bench/demo` | development | about $0.20–0.30 (worst case $0.64, capped) |

## Questions for Bhargavi (answered 2026-10-21: Q1–Q4 as recommended)

| # | Question | My recommendation |
|---|---|---|
| Q1 | Gate the single-question retry for future runs behind a hashed run cap (`retry_failed_batch_singly: true`)? | Yes, so existing runs replay unchanged. A new demo or benchmark run then has it on. |
| Q2 | Is the retry's spend counted against the analysis cap, raised by `--retry-cap`? Or against a separate allowance like the post cap? | The analysis cap, raised: it is analysis work, and R45 and the severity reserve already read that cap. |
| Q3 | `--out-dir` on both scripts, with `cases/demo/` plants defaulting to `bench/demo/`? | Yes. Nothing else writes to `bench/test5/5b/` but `run_case.py`. |
| Q4 | The ledger snapshot: take `ledger-g3pre` now, or after the demo re-run? | After, so it covers all of Phase 3's spend; the records branch gets it last, with the final demo report. |

## Not doing
- No change to `severity/v2` or the severity table. S3 → S4 is the engineer's override, on camera.
- No change to `connector/v2`, `severity_chain/v2` or `recommendation/v2`.
- No full re-run of the demo analysis.
- No re-run of D, E or G until the second grant.
