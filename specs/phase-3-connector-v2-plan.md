# Phase 3 follow-up plan: connector/v2 with handles

Status: approved 2026-10-21 (Bhargavi, with the changes in "Answers" below).

Written 2026-10-21. It follows Bhargavi's go-ahead the same day ("plan connector/v2 with handles", with conditions). This plan is a follow-up within Phase 3, so `specs/phase-3.md` and `specs/phase-3-plan.md` still apply. No code is written until this plan is approved.

## Why

The live extension of D–G (2026-10-21, $0.42) gave 10 valid chains on D and on E, but none on F (3 proposed, 3 rejected) or G (10 proposed, 10 rejected). Code rejected them correctly: each bad link is a damaged copy of a real ID.

## The facts asked for before planning

### G's connector input (rebuilt read-only from the run's records with the same code; no call made)

| Case | Scenario lines sent | Left out | Input tokens, billed | Input tokens, agreed estimate | `connector_max_input_tokens` | Fact IDs listed |
|---|---|---|---|---|---|---|
| D | 121 | 0 | 24,203 | 27,698 | 80,000 | 142 |
| E | 127 | 0 | 24,894 | — | 80,000 | — |
| F | 137 | 0 | 25,187 | 29,726 | 80,000 | 90 |
| G | 110 | 0 | 20,434 | 24,401 | 80,000 | 82 |

- **Nothing was trimmed.** Every scenario line (one per R48 line, with its lead finding) was in the prompt, each with its full finding ID (46–94 characters). The step's own summary also records `left_out: 0`.
- **In G,** every one of the 36 bad finding links copies an ID that *was* one of the scenario lines sent. Ultra dropped the hash parts, for example writing `f:m:S-TOTES:more:pressure:super:C22` for `…:C22:ed67bd729cf1411f`.
- **In F,** Ultra kept the first 8 hex characters of a hash and invented the next 8.
- **Other bad links** (10 in G, 2 in F) are bare object IDs (`LOC-G-WAREHOUSE`, `PORTABLE-PUMP`) or fields the plant does not have (`W-3.notes`, `VENT-HEADER.to_id`).

So the primary bug is **copying long IDs**, not trimming. If v2's input ever has to be cut, it is cut the same way as now (whole lines from the bottom, in R50 order, counted in `left_out`). The handle list is built after the cut, so every handle shown names a line that was sent.

### Does a post-step prompt version change the run ID?

| Run | In the run-ID hash today? |
|---|---|
| D–G (extended) | **No.** Their stored `prompt_versions` predate Phase 3, so no post-step prompt is in them. The post steps load their prompt from the current routing (`load_prompt(name, config)`), and `run_extended` records the versions used. |
| A new run (such as the demo plant) | **Yes, and that is a bug.** `run_settings()` (`runs/case.py`) copies every routed prompt into `Run.prompt_versions`, including `connector`, `lopa_argument`, `recommendation` and `severity_chain`, and `prompt_versions` is hashed. Moving `connector` to v2 would change every new run's ID. The stored value can also disagree with what the post steps load, because they read the current routing. |

**Fix (this plan):**
- `run_settings()` leaves the four post-step prompts out of `prompt_versions`.
- **The post-step caps also leave the hash (Q5):** `connector_max_chains`, `lopa_batch_size`, `recommendation_batch_size` and `lopa_top_n` are left out of a new run's `Run.caps`.
- The hash always covers what `Run.caps` and `Run.prompt_versions` store, so D–G keep their stored IDs and rebuild them from their stored inputs. All four stored `lopa_top_n` in their hashed caps, and their post steps keep reading it (G8).
- The post-step settings, with their source, and the post-step prompt versions are recorded on `run_extended`, as extension already records them.
- A run records the post-step prompt versions on its `run_extended` event, emitted when it first enters the post steps:
  - from `extend_run.py` for an old run, as now;
  - from the `chains` step itself for a new run that reaches it with no `run_extended` event yet.
- New tests check both that a post-step prompt version is not in the run-ID inputs and that changing it leaves the run ID the same.

## What v2 does

### Line handles
- The connector's scenario block lists each line as `L1`, `L2`, … in the order sent, and shows no finding IDs.
- Ultra links only by handle. Code maps each handle back to its finding ID exactly.
- An unknown handle (for example `L999`, `l3` or `L3 `) rejects the whole chain, with that reason, as an unknown ID does today.

### Fact handles
- The fact block becomes a numbered list, `P1`, `P2`, …, each with its fact ID and value. Ultra links facts only by handle.
- **The list is limited to facts on these objects** (Bhargavi, 2026-10-21):
  - the scenario objects of the lines sent: each line's failing components and its section's objects, the same set LOPA uses for candidate layers. The section objects are needed so that a finding whose only failing component is a procedure step still reaches its equipment;
  - their locations (the `location_id` of each such object);
  - their utilities: a utility that is an endpoint (`from_id` or `to_id`) of a line of theirs, of a line ending at one of them, or of one of their heat-source lines (`heat_sources.via_line_id`);
  - for the objects above: the relief devices whose `protects_id` is one of them, those devices' inlet valves, each heat source's `isolating_valve_ids`, and the valves on lines that start or end at one of them.
- The list is in sorted fact-ID order, so the same run gives the same handles.
- An unknown `P` handle rejects the chain. A bare object ID can no longer be written, because only handles are accepted.

**Demo-plant check (test):** a finding on S-EA-425B whose only failing component is P-REB-START-2 has `HV-B-SIN.normal_position` and `RV-PATH-EA425B.inlet_valve_ids` in its fact list.

### Unchanged
- Chains are stored with real finding and fact IDs. `Chain.links`, `ids.chain_id` and the contract do not change, and the handles exist only in the prompt and its answer.
- The other checks are kept: at least 2 links, at least one a finding, at most `connector_max_chains`, and "possibly more than two independent failures" flagged, never filtered.

## Re-running the post steps from `chains`

`extend_run.py <run_id> --rerun-from chains --post-cap <usd> --use development [--name …]`:
- **Accepted for:** a run that is `finished`, or `stopped_cap` at its post cap, and whose `chains` step has run.
- **What it does:** it re-runs `chains → chain_severity → lopa → recommendations → ranked`, so chain severity, LOPA and recommendations are all redone. The analysis is not touched, and the run ID stays the same.
- **The event log:** a `run_extended` event names the re-run (`rerun_from: chains`), the post prompt versions and the settings used. A new event lists every superseded record ID. Questions Q1 and Q2 below concern the event type and whether the cap counts the new pass only.

**What happens to the old records** is question Q1 below, because the stored rows are keyed by (run ID, record ID) and the IDs repeat. My recommendation:
- Before the re-run, copy each old chain, LOPA record and recommendation, and the old post-job model call records, verbatim into a new `superseded_records` table, with the pass they belonged to.
- Then clear them from the live tables, so the re-run can write records with the same IDs.
- No record is ever changed, and nothing is lost. The event lists every superseded ID, and the run dump can serve them.
- The table is additive, so `guideword.db` needs no migration.

**Repeated requests:** a request identical to one made in the old pass (for example an unchanged LOPA batch) is served from the response cache at $0 and recorded as a cache hit. The gateway's "repeated request" refusal reads only the live model-call records, so archiving the old pass's calls lets this work.

**Spend:**
- R45 compares `spent_usd` with the sum over live and superseded call records.
- The post cap counts the new pass only (Q2), and the phase cap and use allowance still count every call through the ledger.

## Pull requests, in order

| # | Branch | What | Review |
|---|---|---|---|
| 1 | `phase-3/connector-v2-prompt` | `prompts/connector/v2.md` drafted (handles, fact handles, "link only by handle", reason field, no numbers asked); no routing change yet | **Bhargavi reviews the wording**, runs `scripts/prompt_leak_check.py` ($0) |
| 2 | `phase-3/connector-v2` | Line and fact handles; the fact-list limit; the run-ID fix; `--rerun-from chains`; superseded records; routing `connector: v2`; `docs/feedback-log.md` entry; decisions | after PR 1 merges |

### Tests first (all $0, fake gateway)
- `test_connector_v2_maps_line_and_fact_handles_back_to_exact_ids`
- `test_an_unknown_line_or_fact_handle_rejects_the_chain`, covering `L999`, `P0`, lower case, extra spaces, a raw finding ID and a bare object ID.
- `test_the_fact_list_holds_only_facts_on_components_their_locations_and_utilities`
- `test_handles_are_built_after_the_input_is_cut` (a cut list has no handle for a line not sent)
- `test_a_post_step_prompt_version_is_not_in_the_run_id_inputs`
- `test_changing_a_post_step_prompt_version_keeps_the_run_id`
- `test_changing_lopa_top_n_keeps_a_runs_id` (and the other three post-step caps)
- `test_d_to_g_stored_run_ids_are_unchanged` (each stored ID rebuilt from its stored inputs, the four IDs pinned)
- `test_the_demo_fact_list_reaches_the_reboilers_inlet_valve_and_relief_path` (S-EA-425B, only P-REB-START-2 failing)
- `test_the_run_dump_lists_superseded_records_marked_as_superseded`
- `test_copy_and_clear_happen_in_one_transaction` (a failure while clearing leaves the live tables and `superseded_records` as before)
- `test_a_new_run_records_its_post_prompt_versions_on_run_extended`
- `test_rerun_from_chains_redoes_chain_severity_lopa_and_recommendations` (same run ID; no analysis call sent)
- `test_rerun_supersedes_old_records_through_the_event_log_and_deletes_nothing`. Every old record is in `superseded_records`, byte-identical, and listed on the event.
- `test_rerun_serves_unchanged_requests_from_the_cache_at_zero_cost`
- `test_rerun_spend_matches_records_including_superseded_calls` (R45)
- `test_rerun_is_refused_for_an_unfinished_run_or_one_never_extended`
- A guard test: `connector/v2` has every data slot through `as_data`.

## Live calls and spend (Bhargavi starts each one)

| Step | Use | Expected |
|---|---|---|
| `prompt_leak_check.py` on v2 | — | $0 |
| `--rerun-from chains` on D, E, F, G | development | about $0.40 (the first pass cost $0.42; unchanged LOPA and recommendation batches are cache hits) |
| Demo plant run | development | held until PR 2 merges |

Phase 3 has spent $0.42 of $2.50; development has $2.85 left.

## `docs/feedback-log.md` entry (PR 2)

> 2026-10-21 | Nemotron-3 Ultra (connector) | Asked to link chains by exact finding IDs (46–94 characters, two 16-hex hashes), Ultra shortened or rewrote them: G 36 of 36 finding links wrong, F 2 bad (each a scenario line it was shown); it also used bare object IDs as facts. Input was 20–25k tokens, nothing trimmed. | Long opaque IDs are not reliably copied; short handles mapped back by code avoid it. A "copy exactly" mode or constrained decoding over a given ID list would help.

## Answers (Bhargavi, 2026-10-21)

| # | Answer |
|---|---|
| Fact list | Also the relief devices protecting the listed objects, those devices' inlet valves, each heat source's `isolating_valve_ids`, and valves on lines that start or end at a listed object; tested on the demo plant (above). |
| Q1 | Yes: `superseded_records`. Copy and clear in one transaction. The run dump lists superseded records, marked as superseded. |
| Q2 | Yes: the re-run's post cap counts the new pass only. |
| Q3 | Yes: a re-run is refused when an override names a post record. |
| Q4 | Yes: a field on `run_extended` (`superseded_ids`). `Event.payload` is a free-form object in the contract (`dict[str, Any]`), so no contract shape changes; the PR says so. If the export of the run dump needs the superseded records, that is a contract change and goes in its own `contract/…` branch, with types regenerated. |
| Q5 | Move the post-step caps out of the hash too, recorded on `run_extended` with the prompt versions. Test that D–G's stored run IDs are unchanged and that changing `lopa_top_n` keeps a run's ID. |
| Q6 | Yes, as recommended. |
| Wording | PR 1 (the v2 wording) is Bhargavi's review. It must say "link only by handle", and its examples must use no real ID from D–G (made-up handles and facts only), so the prompt itself does not teach copying. |

## Questions for Bhargavi (answered above)

| # | Question | My recommendation |
|---|---|---|
| Q1 | Old post records on a re-run. The live tables are keyed by (run ID, record ID) and the IDs repeat, so the old and new records cannot share a table. | A `superseded_records` table holding each old record verbatim, plus its pass, with the event listing every ID. The other option is a pass column in the primary key, which needs a migration of `guideword.db` and a visible counter beyond attempt and `seq` (CLAUDE.md §3 allows only those two). |
| Q2 | Does the re-run's post cap count the new pass only? | Yes. The old pass's spend still counts in the phase cap, the use allowance and `spent_usd`. |
| Q3 | A re-run when overrides name a post record (`lopa:…`, `rec:…`, `ch:…`)? | Refuse the re-run and list the overrides. None exist on D–G. |
| Q4 | New event type for the superseded list (`post_superseded`), or a field on `run_extended`? | A field on `run_extended` (`superseded_ids`), so there is no enum change and no contract change. |
| Q5 | The post-step caps (`connector_max_chains`, `lopa_batch_size`, `recommendation_batch_size`, `lopa_top_n`) are also under the hashed `run:` block. Do they leave the hash too, like the prompts? | Leave them as they are in this plan, because a cap change is rarer and PR 2 of Phase 3 put them there on purpose. Raise them again if one has to move. |
| Q6 | What counts as "their utilities"? | The rule above: a utility at an endpoint of a component line, a line ending at a component, or a component's heat-source line. |

## Not doing
- No change to `Chain.links`, chain IDs, the contract or the schema of any record.
- No fuzzy or prefix matching of IDs. A bad handle still rejects the chain.
- No change to the other three post-step prompts.
- No demo plant run until PR 2 merges.
