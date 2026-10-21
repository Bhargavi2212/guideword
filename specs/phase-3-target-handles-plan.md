# Phase 3 follow-up plan: handles for chain and line targets, and handle-free chain text

Status: approved 2026-10-21 (Bhargavi, with the answers below).

Written 2026-10-21, after the connector/v2 re-runs of D–G, and following Bhargavi's go-ahead the same day. `specs/phase-3.md`, `specs/phase-3-plan.md` and `specs/phase-3-connector-v2-plan.md` still apply. No code is written until this plan is approved.

## What the records show (reported before fixing, as asked)

### Why F's chains have no severity

F's one `chain_severity` call (`mc:85c90233d14e3fcf`, `severity_chain/v1`) was read from its stored record; no call was made.

| Check | Result |
|---|---|
| Validation error | **No.** Outcome `ok`, valid JSON, one attempt. |
| Refusal | **No.** |
| Retries exhausted / cut off | **No.** `finish_reason: stop`; 4,809 output tokens, 4,093 of them reasoning. |
| Echoed chain ID that didn't match | **No.** Ultra answered 2 chains, and both IDs match stored chains exactly (198–609 characters). |
| **What happened** | **Ultra rated only the last two of the 10 chains sent (positions 9 and 10).** Its reasoning opens: *"We are given multiple chains (the last batch includes two chains)… We have two chains in the last batch"*. Code then marked the 8 it left out "not assessed", as G3 says, so they get no LOPA. |

So the cause is not ID copying. Ultra misread a long input: 10 chains, 5–15 links each written out in words, each headed by an ID up to 609 characters, about 9,000 input tokens. It took the tail of the list for "the last batch". The handles fix the long IDs, but they may not stop this misreading on their own, which is why Q1 proposes smaller batches and one re-ask.

### Do the other two post steps echo long IDs?

| Job | What it must echo | On D–G |
|---|---|---|
| `lopa_argument/v1` | `target_id`: a lead finding ID (43–94 characters) or a **chain ID (up to 609 characters)**; `layer_id`: a safeguard or relief device ID (short plant IDs) | D, E, G: no line flagged "left out of the argument answer". F made no argument call, because none of its lines or chains has a candidate layer (correct; no call is needed). |
| `recommendation/v1` | `target_id`: a lead finding ID or a chain ID | No line flagged "no recommendation: left out" on any case. |

Both are exposed in the same way as the chain severity step, through the chain IDs, even though nothing was lost this time.

### Handles in stored chain text

The connector wrote its own handles into the chain text it returned, for example D's descriptions "(L20)" and "(L25)" and F's "(L14)" and "(L119)". Code stores that text as given. Once the v2 prompts number their own lines `L1…`, an "L20" in a chain's text would point at the wrong line.

### No-severity chains on the shortlist

F's 8 unrated chains are on its shortlist, each with `no_lopa_reason: "no severity"`, but their `flags` are empty, so a card shows no warning.

## What this plan does

### 1. Handles for targets (three new prompt versions, Bhargavi's review)

| Prompt | Handles shown | Mapped back by code |
|---|---|---|
| `severity_chain/v2` | each chain `C1…`, its links in words (no finding or chain IDs) | `chain_id` → `C<n>` |
| `lopa_argument/v2` | each target `L<n>` (a line) or `C<n>` (a chain); layers keep their short plant IDs | `target_id` → `L<n>`/`C<n>`; `layer_id` checked as today |
| `recommendation/v2` | each target `L<n>` or `C<n>` | `target_id` → `L<n>`/`C<n>` |

- Each prompt numbers its own handles in the order it sends them, and says "answer only by handle".
- An unknown handle drops that item, exactly as an unknown ID does today. The item is then "left out", "not assessed" or "no recommendation".
- Examples use made-up handles only, never a real ID from D–G.
- Routing moves the three prompts to v2 in PR 2.

### 2. Chain text without handles (in PR 2, which builds the handles too)

After mapping, code replaces every `L<n>` and `P<n>` token in a chain's `description` and `reason` (a whole token: `\bL\d+\b`, `\bP\d+\b`):
- **`L<n>`** becomes the mapped line's lead finding's **question ID**;
- **`P<n>`** becomes the **fact ID**.

A token that names a handle not in the sent list is left as it is, and the chain is flagged "unresolved handle in text".

**The raw answer stays unchanged** in the connector's model-call record (`raw_response`). Only the stored chain's display fields carry the substitution. When any token was replaced, the chain is flagged "handles in text replaced by code", so the substitution is recorded as code's, not the model's (Q3).

### 3. "No severity" never hides a chain

A chain with no severity is on the shortlist with the flag **"no severity — no LOPA"**:
- in the run report's shortlist row (`flags`);
- in the API card (`ShortlistItem.flags`, contract v1.5).

It stays listed in `lopa_none` too.

### 4. Chain severity completeness (Q1)

My recommendation:
- `chain_severity_batch_size: 5` in `caps.yaml`, the same size as `lopa_batch_size` and `recommendation_batch_size`. It is recorded on `run_extended` and not hashed, like the other post-step caps.
- Each batch's left-out chains are asked once more, alone, in a follow-up batch. A chain left out twice is "not assessed", as today.

## Pull requests, in order

| # | Branch | What | Review |
|---|---|---|---|
| 1 | `phase-3/target-handles-prompts` | this plan; `prompts/severity_chain/v2.md`, `prompts/lopa_argument/v2.md`, `prompts/recommendation/v2.md` (not routed yet) | **Bhargavi reviews the wording**, runs `prompt_leak_check.py` on each ($0) |
| 2 | `phase-3/target-handles` | target handles in the three steps; chain-text substitution and its flags; the "no severity — no LOPA" flag; Q1's batching and re-ask; routing at v2; decisions; feedback-log entry for the "last batch" misreading | after PR 1 merges |

### Tests first (all $0, fake gateway)
- `test_chain_severity_v2_maps_chain_handles_back_and_drops_an_unknown_one`
- `test_lopa_argument_v2_maps_line_and_chain_targets_back_and_drops_an_unknown_one`
- `test_recommendation_v2_maps_line_and_chain_targets_back_and_drops_an_unknown_one`
- `test_no_v2_prompt_input_shows_a_finding_or_chain_id`
- `test_chain_text_handles_become_question_and_fact_ids` (exact tokens only, so `L20x` and `PL1` are untouched)
- `test_an_unsent_handle_in_chain_text_is_left_and_flagged_unresolved`
- `test_the_connectors_raw_answer_is_unchanged_in_its_model_call`
- `test_no_chain_text_sent_to_a_v2_prompt_contains_a_connector_handle`
- `test_a_chain_with_no_severity_is_on_the_shortlist_flagged_no_severity_no_lopa` (report row and API card)
- `test_chain_severity_goes_in_batches_and_re_asks_left_out_chains_once` (Q1)
- `test_the_re_ask_names_exactly_the_missing_handles_and_the_answer_count_is_checked`
- `test_two_lines_sharing_a_question_id_are_written_with_their_cause_id` (Q4)
- `test_no_v2_prompt_or_user_message_says_batch_and_each_states_its_count`
- `test_a_chain_left_out_twice_is_not_assessed`

## Live calls and spend (Bhargavi starts each one)

| Step | Use | Expected |
|---|---|---|
| `prompt_leak_check.py` on the three v2 prompts | — | $0 |
| F: `--rerun-from chains` after PR 2 merges | development | about $0.10. The connector request is unchanged, so it is a cache hit at $0 with the same chains, and their text is cleaned by code. Chain severity, LOPA and recommendations are paid on the new prompts. |
| D, E, G | — | **wait for the second grant** (Bhargavi, 2026-10-21) |
| Demo plant run | development | waits for PR 2 |

Phase 3 has spent $0.87 of $2.50; development has $2.40 left.

## Answers (Bhargavi, 2026-10-21)

| # | Answer |
|---|---|
| Q1 | Yes: batches of 5, and one re-ask for exactly the missing handles. Code checks the answer count against what was sent. |
| "Batch" in v1 | Reported: `severity_chain/v1` says "Every chain ID in the batch appears exactly once" and `"<an ID from the batch>"` in its answer format, and the user message code sends says "Give the severity of every chain in the batch". `lopa_argument/v1`, `recommendation/v1` and the recommendation step's user message use the same word. None states how many items were sent. **So the v2 prompts and their user messages never use "batch" or any group label for the list. Each states the exact count and handle range**, for example "the 5 chains below, C1 to C5", through code-only slots `{{count}}` and `{{handles}}` (the handles listed, since a LOPA or recommendation call can mix `L` and `C` targets). |
| Q2 | Agreed: F re-runs after PR 2 merges; D, E and G wait for the second grant. `docs/decisions.md` records that D, E and G stay on the v1 post prompts until then. |
| Q3 | Yes: the flag "handles in text replaced by code", only on chains where a replacement happened. |
| Q4 | Confirmed: the question ID. If two lines sent share a question ID, each is written "<question ID> (<cause ID>)" so the replacement names one line; tested. (If two such lines also share a cause ID, which happens only for two outside-library causes on one question, the lead finding ID is written instead, so it always names one line.) |

## Questions for Bhargavi (answered above)

| # | Question | My recommendation |
|---|---|---|
| Q1 | F's loss was a misreading of a long list, not a bad echo. Do we add batching and a re-ask for left-out chains? | Yes: `chain_severity_batch_size: 5` (caps.yaml, recorded on `run_extended`, not hashed), and left-out chains re-asked once, alone. Without it, the handles alone may not stop "last batch" misreadings. |
| Q2 | Your two messages differ on D, E and G: one says they wait for the second grant, the other that their re-run is cache hits except the text substitution, at $0. A re-run from `chains` reuses the connector answer from the cache at $0 and cleans the text, but chain severity, LOPA and recommendations then run on the new v2 prompts, which is paid (about $0.30 for the three). | Follow "wait for the second grant". D–G keep their leaked handles in chain text until then. Their reports are not sent to any v2 prompt meanwhile. |
| Q3 | How is the substitution "recorded as code's"? | A chain flag, "handles in text replaced by code", whenever a token was replaced, plus the untouched raw answer in the model call. No new record field and no contract change. |
| Q4 | Should `L<n>` become the lead finding's **question ID** or its **finding ID**? You wrote question ID. | Question ID, as you wrote. It is short and readable, and the finding is one click away through the chain's links. |

## Not doing
- No change to chain IDs, finding IDs, `Chain.links` or the contract.
- No fuzzy matching. An unknown handle drops the item.
- No change to `severity/v2` or the connector.
- No re-run of D, E or G until the second grant.
