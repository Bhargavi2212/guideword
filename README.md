# Guideword

Guideword prepares a HAZOP study from a plant file. Code builds every question the study must answer (guideword × parameter per section, every chemical pair, every no-flow line, procedure step, planned job, dust and relief question). A Nemotron 3 Ultra orchestrator agent on Nebius Token Factory works through them with six specialist agents and tools, and code ranks the results by LOPA protection gap with evidence: physics calculations, accident precedent and a Tennessee Eastman simulation. Every number traces to a plant fact, a model call or a published reference table. The engineer decides.

Built for the Nebius × NVIDIA Global AI Hackathon (Best Apps and Agents). Licence: Apache 2.0.

## Results: the held-out benchmark

**Measured: Guideword put the real cause in the top 3 on 0 of 3 held-out cases.** The two baselines, run on the same plant files with the same model, scored 2 of 3 and 3 of 3. Everything that produced that number is in this repo, and so is what we found when we read the run records afterwards: the pipeline had found the cause in every case and two lines of our own code hid it. Both are reported below, kept apart.

### How the benchmark was built

- **Eight cases, written blind.** A separate Claude session, run once as a scheduled task on 2026-10-13 and told not to read this repo, wrote eight lesser-known accidents (four US, four from the UK, NL, JP and FR) as the plant looked before the accident, with unrelated equipment mixed in, plus a sealed answer key for each. They live in [cases/heldout/](cases/heldout/) with the writer's [selection log](cases/heldout/selection-log.md).
- **Sealed, then frozen.** Each package and key is hashed in [SEALS.txt](cases/heldout/SEALS.txt), committed here as [bench/heldout-seals.txt](bench/heldout-seals.txt) before any run. The plant files were converted by a fresh session and hashed in [bench/heldout-frozen.txt](bench/heldout-frozen.txt) before anyone read a key. `pytest backend/tests/bench/test_heldout_published.py` checks every published file against both.
- **Honour system, and its gap.** The builder owned the folder and did not open it before Phase 6. The folder had no git history when it was sealed, so the seal date (2026-10-14 02:41 UTC, 21 minutes after the cases were written) rests on file timestamps, which a local disk can change. We state this rather than claim more.
- **Frozen pipeline.** Every run used tag `phase6-freeze-3` (`67bd9f04315c63b67db08894765497580c2a7119`). Prompts, routing, reference tables and code did not change between runs.
- **Memorisation probe.** Each case was first shown to Nemotron 3 Ultra and it was asked whether it knew the accident. It named the company and site for cases L and N, so they were excluded. K, M, P, Q, R and S were kept.
- **Budget.** The benchmark allowance was $5.19 of a $25 total. K, M and P ran under a per-run cap of $1.40 plus $0.30 for the post-analysis steps; the stop rule then refused a fourth case. R and S were never converted or run.
- **Three configurations per case**, in a fixed order: Baseline A (one prompt plus a step-by-step checklist, Nemotron 3 Ultra), Baseline B (one plain prompt, Nemotron 3 Ultra), then Guideword.
- **Two blind graders.** The builder and a second Claude session each scored the top 10 of every configuration against the sealed key, from sheets that label the configurations X, Y and Z. A hit means the key's root cause; a partial is shown and never counted. The builder's score is the headline; the second grader's is reported beside it.

### Headline (as measured, [bench/heldout/results.md](bench/heldout/results.md))

| Configuration | Top 3 | Wilson interval (0.95) | Top 10 | Wilson interval (0.95) | Partials (not counted) |
|---|---|---|---|---|---|
| Guideword | 0 of 3 | 0.00 to 0.56 | 0 of 3 | 0.00 to 0.56 | 1 |
| Baseline A (checklist) | 2 of 3 | 0.21 to 0.94 | 2 of 3 | 0.21 to 0.94 | 1 |
| Baseline B (one prompt) | 3 of 3 | 0.44 to 1.00 | 3 of 3 | 0.44 to 1.00 | 0 |

| Case | Guideword | Baseline A | Baseline B | Guideword's run |
|---|---|---|---|---|
| K | miss | miss | hit | stopped at its cap, 10 questions open; $1.45; 43 min |
| M | miss | hit | hit | finished; $1.28; 29 min |
| P | miss | hit | hit | stopped at its cap, 180 questions open; $1.47; 40 min |

A Guideword run that stops at its cap counts as a miss. Exact McNemar against Baseline A p = 0.50 and against Baseline B p = 0.25: with n = 3 no difference can be claimed either way. The graders agreed on 8 of 9 top-3 calls (the one disagreement: Baseline A on K, builder miss, second grader hit). Total paid for the benchmark: $4.19.

### One more case after the first fix: Q, a miss

After the benchmark closed we added three cause-library rows (below) and spent $0.86 more of the allowance to run case Q from tag `phase6-freeze-post-fix-q` (`0def2bcc67b0daf0f3cd2bee498cd5b3fb9ceff0`), graded blind by both graders in the same way. It is one case and is never added to the table above.

| Case | Guideword | Baseline A | Baseline B | Guideword's run |
|---|---|---|---|---|
| Q | miss (both graders) | miss in the top 3, hit at 10 (both graders) | builder: partial at 1; second grader: hit at 1 | stopped at its cap, 351 questions open; $1.46; 43 min |

Records: [bench/heldout-post/](bench/heldout-post/). Q's mechanism is not one the three new rows cover.

### What the records showed, and what we changed

Reading the four runs' records after grading (a departure from our own isolation rule, logged in [docs/decisions.md](docs/decisions.md) on 2026-10-29; nothing under the benchmark folders was changed) showed one thing in every case: **the whole-plant pass had put the real mechanism at hypothesis rank 1**, and the pipeline had confirmed it with a finding. Two deterministic steps then hid it from the shortlist the graders read:

1. **The cause library was too generic.** The 26-row library had no "corrosion thins a pipe wall", "control valve passes when closed" or "process change without a hazard review", so the specialists chose the nearest listed cause instead of flagging an outside-library one. Fix (Phase 7, after the benchmark): rows C27 to C29 in [reference/causes.csv](reference/causes.csv), each mapped to an existing sourced initiating-event frequency, labelled post-benchmark.
2. **The shortlist re-sorted and re-worded the confirmed tier.** The LOPA gap sort moved M's rank-1 hypothesis to line 7, and each card showed the lead finding's question title ("Loss of cooling water supply", "Control valve fails open") where the hypothesis said "runaway polymerisation generating heat faster than E-1 can remove" or "steam leaks past non-tight FV-A/FV-B and closed manual valves into the reboilers of idle C-1". The blind sheets show what the card shows, so the graders scored the generic words. Fix (Phase 8): the confirmed tier keeps the model's order and each confirmed line leads with the hypothesis's mechanism, with the finding beneath it as "Confirmed by". The gap still orders the also-found tier and stays on every card.

**Post-hoc re-render of the same stored runs with the Phase 8 code ($0, no model call).** These numbers are not a score. The measured table above stands.

| Case | Line of Ultra's rank-1 hypothesis, as graded | After Phase 8 | Automatic exact-phrase match, before → after | Our own non-blind reading of the new line 1 |
|---|---|---|---|---|
| K | 1 (generic words) | 1 (its mechanism) | 9 → 1 | partial: the runaway, with the recipe change at line 12 |
| M | 7 | 1 | none → none | hit |
| P | 2 | 1 | none → none (the key's phrases lack Ultra's wording) | hit |
| Q | 3 | 1 | 20 → 20 | partial |

A fresh blind pass by a second grader on the re-rendered sheets would turn the last column into a post-hoc human number; it would still be reported beside the headline, never in it.

### Limits

- n = 3 (plus one post-fix case). The intervals above are the honest width of that.
- The per-run spend cap stopped three of the four Guideword runs with questions open (10, 180 and 351). A stopped run counts as a miss.
- One of the two graders is the builder; the second is a Claude session. The post-hoc reading is ours and not blind.
- The memorisation probe was run on Nemotron 3 Ultra only, the model every configuration uses for its whole-plant judgement.
- Four cases out of eight were run. Every published key is now public, so these eight cases cannot serve as a held-out set again.

### Rerun it

From the freeze worktree with `NEBIUS_API_KEY` set and the budget ledger in place (every call is capped and written to the ledger):

```powershell
python scripts/heldout_verify.py cases\heldout --only k,m,p,q
python scripts/probe_heldout.py cases\heldout --store guideword-benchmark.db --ledger budget\ledger.jsonl --out bench\heldout
python scripts/probe_judgement.py --probe-dir bench\heldout\probe --keys cases\heldout\keys --csv bench\heldout\probe_judgement.csv
python scripts/run_benchmark.py cases\heldout --store guideword-benchmark.db --ledger budget\ledger.jsonl --frozen bench\heldout-frozen.txt --judgement bench\heldout\probe_judgement.csv --out bench\heldout
python scripts/heldout_score.py --keys cases\heldout\keys --out bench\heldout
python scripts/heldout_sheets.py --keys cases\heldout\keys --out bench\heldout
python scripts/heldout_results.py --out bench\heldout
```

The development-set results (cases D to G, used for tuning, never pooled with the above) are in [bench/test5/results.md](bench/test5/results.md).

## Nemotron on Nebius Token Factory

Three Nemotron tiers do three kinds of job (a fourth, Nemotron 3 Nano, is the fallback), routed by [config/routing.yaml](config/routing.yaml): Nemotron 3 Ultra reads the whole plant once and proposes ranked hypotheses, runs the orchestrator, links chains, writes the LOPA argument and the recommendations; Nemotron 3 Super answers the hard specialist questions and suggests sections; Nemotron 3.5 Lightning answers the bulk of the question grid in batches. Code builds the question list, does every piece of arithmetic (LOPA, independence, ranking, coverage) and validates every model response against a Pydantic schema, so a model never sets a number. A whole-plant run on a held-out case cost $1.28 to $1.47 at the benchmark's cap. Every call passes a budget guard and lands in a ledger; the friction we hit with each tier (truncation at the token limit, schema answers in place of tool calls, batch re-asks) is in [docs/feedback-log.md](docs/feedback-log.md).

## Setup (Windows, PowerShell)

```powershell
conda deactivate
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip pip-tools
pip-sync backend/requirements.txt backend/requirements-dev.txt
copy .env.example .env   # then fill in keys; never commit .env
pytest backend -q
```

Frontend: Node 22 LTS, `cd frontend; npm ci; npm run dev`.

See `PROJECT.md` for the full design and `CLAUDE.md` for contribution rules.
