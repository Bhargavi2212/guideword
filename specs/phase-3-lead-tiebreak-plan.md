# Phase 3 follow-up plan: a confirmed line's lead tie-break

Status: approved 2026-10-21 (Bhargavi: Q1 re-run with the rule, recorded on `run_extended`; Q2 accept, with a §23 known limit; Q3 re-run from `lopa`).

Written 2026-10-21, after the demo run's `--retry-failed` extension and Bhargavi's conditions the same day. The earlier Phase 3 plans still apply. No code is written until this plan is approved.

## The rule today

- **Where the lead comes from:** `tiered()` (`backend/guideword/ranking/tiers.py`) takes a confirmed line's **first supporting finding in code's ranking order** as its lead.
- **That order** is `rank_findings()`'s key (`backend/guideword/ranking/rank.py`): risk rating, severity, initiating frequency, protection (adequate last), and finally the **finding ID as a plain string**.
- **The effect:** among findings that tie on everything else, `f:env:…` sorts before `f:m:…`, so an environment question's finding leads over the hypothesis's own section's findings.

## The change (Bhargavi's conditions)

- **Ties only.** Among supporting findings with the same rating, severity, frequency and protection, prefer one whose **question's section contains a hypothesis component** (the section's `object_ids` ∩ the hypothesis's `component_ids`), then the finding ID as now.
- **Never touched:** severity, likelihood and protection adequacy keep their order and are never outranked.
- **It applies to a confirmed line's lead only.** Which hypothesis owns a finding, the also-found fold and the global ranking are unchanged.
- **Gated** by a hashed ranking setting, `ranking.lead_prefers_own_section: true` in `caps.yaml`, read from the **run's stored** `caps.ranking`. Views of D–G and of the G2b E/F runs, whose stored ranking lacks the key, read exactly as before.
  - **The demo run** started before the setting existed, so its stored caps lack it too. It takes the rule through a re-run (below), which records the setting on its `run_extended` event, and the views read it from there. *(Q1: or set it only for runs started after the change, which would leave the demo as it is.)*

## What it does on the demo run (checked at $0 against the run's records)

| Line | Lead today | Lead with the rule | Why |
|---|---|---|---|
| #1 confirmed (EA-425A tube rupture, C12) | `f:env:C4-HEAVIES:air…` | **`f:m:S-EA-425A:less:flow…`** | a tie (medium, S3, 0.001, inadequate vs unknown protection, which sort the same); S-EA-425A contains EA-425A |
| #2 confirmed (EA-425B tube rupture, C12) | `f:env:C4-HEAVIES:air…` | **unchanged** | **not a tie**: S-EA-425B's own C12 findings were rated **S2** (low), the env findings S3 (medium) |
| #3, #4 | `f:env:C4-HEAVIES:air…` | unchanged | no own-section finding ties |
| #5 (external fire, C22) | `f:env:C4-HEAVIES:air…` | `f:m:S-DA-406:more:pressure…` | tie; S-DA-406 contains DA-406 |
| #7 (line leak, C20) | `f:env:C4-HEAVIES:air…` | `f:m:S-L-B-SIN:less:pressure…` | tie |

**So the rule fixes reboiler A's line, but not reboiler B's.** On the B line, the severity step rated the reboiler's own C12 findings S2, below the env findings' S3. "Ties only" correctly leaves that alone. Reboiler B's card would still cite the C4-heavies-and-air finding (Q2).

**The new leads have no LOPA record or recommendation yet.** LOPA targets a line's lead, so after the change the demo needs a post-step re-run.

## The re-run: from `lopa`, not `chains`

- **Chains are unaffected:** their links are finding IDs and still valid, and a chain's tier is computed on read from its member lines. The connector would see different lead text, but nothing it produced is wrong.
- **So `--rerun-from lopa`** is enough. It is a new option beside `chains`: it supersedes the LOPA records and recommendations, keeps the chains and their severities, and re-runs `lopa → recommendations → ranked`.
- **Cost:**
  - **LOPA batches** go 5 targets per call, in display order. Only the batches holding a changed lead differ, about 2 of 4 calls; the rest are identical requests, served from the cache at $0.
  - **Recommendations** work the same way: about 2 of 4 calls differ.
  - **Expected:** about **$0.04–0.07**, worst case about $0.10 if every batch differs. From `chains` would add the connector ($0.04) and chain severity ($0.02), about $0.10–0.15.
  - Phase 3 has $0.36 left.
- **Checked after the run** (read-only, before the demo report): reboiler A's new lead (`f:m:S-EA-425A:less:flow…`), #5's and #7's each have a LOPA record, and a recommendation where its gap is above 1.

## The video (Bhargavi)
- **No `change_credit` on the "does not apply" record:** the valve is closed, so crediting the layer would be false. The video shows the chain record with **"no credit — inlet valve HV-B-SIN closed"**.
- **Added to `PROJECT.md` §23 Known limits:** "No override to say a layer applies and let code re-check its credit." The engineer can credit a layer (`change_credit`), but cannot tell code that Ultra's "does not apply" was wrong and have the inlet-valve rules run.

## Also in this PR
- **The retry summary key:** the `retry_failed` step's summary puts the question's result under `status`, and the machine's own `status` field overwrites it. It is renamed `outcome`, with a failing test first.
- **The records follow-up** (after the re-run): the new demo report, the results note updated, and the ledger snapshot `budget/ledger-g3pre.jsonl`, which then covers all of Phase 3.

## Pull requests

| # | Branch | What |
|---|---|---|
| 1 | `phase-3/lead-tiebreak` | this plan; the gated tie-break; `--rerun-from lopa`; the summary-key fix; `PROJECT.md` §23 limit; decisions |
| 2 | `phase-3/records-final` | after Bhargavi's re-run: the demo report, the results note, `budget/ledger-g3pre.jsonl` |

### Tests first (all $0)
- `test_a_tie_prefers_a_finding_from_the_hypotheses_own_section`
- `test_the_tie_break_never_outranks_severity_likelihood_or_protection` (an own-section S2 never leads an S3)
- `test_ownership_the_fold_and_the_global_rank_are_unchanged`
- `test_runs_stored_without_the_setting_read_exactly_as_before` (D–G and E/F, from their stored inputs)
- `test_rerun_from_lopa_keeps_chains_and_supersedes_lopa_and_recommendations`
- `test_after_the_change_the_new_leads_get_lopa_and_recommendations`
- `test_the_retry_summary_records_the_questions_outcome`

## Live call (Bhargavi starts it)

| Step | Use | Expected |
|---|---|---|
| `extend_run.py run:4e6842d31fbdee3b --rerun-from lopa --post-cap 0.30 --out-dir bench/demo` | development | about $0.04–0.07 (worst about $0.10) |

## Questions for Bhargavi (answered 2026-10-21, as recommended)

| # | Question | My recommendation |
|---|---|---|
| Q1 | The demo run's stored caps lack the new setting. Does it take the rule through its re-run (recorded on `run_extended`), or keep today's leads? | Through the re-run, so the demo shows the rule. Then the ranking setting is read from the latest `run_extended` when present, else from the stored caps. |
| Q2 | Reboiler B's line keeps the env lead, because its own findings were rated S2, not tied. Accept that for the demo? | Accept it, and say so in the known limits. The alternative is letting an engineer's `change_severity` move leads on read, which changes which line gets LOPA without a re-run, so I would not do it now. |
| Q3 | `--rerun-from lopa` instead of `chains`? | Yes: chains stay valid, and it is the cheaper re-run. |

## Built

- [x] PR 1 `phase-3/lead-tiebreak`: the gated tie-break, `--rerun-from lopa`, the summary-key fix, the two `PROJECT.md` §23 limits, decisions.
- [ ] Bhargavi re-runs the demo from `lopa` (about $0.04–0.07); then the records PR with `budget/ledger-g3pre.jsonl`.

## Not doing
- No change to severity, likelihood, the risk matrix or protection order.
- No change to any prompt.
- No re-run of D, E or G.
