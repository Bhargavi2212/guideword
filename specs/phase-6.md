# Phase 6 — Benchmark: the held-out accidents, run once and scored blind

Status: approved 2026-10-25 (Bhargavi), with the G2 answer written into P6-2 and 6.4 (plan G12).
Written by Cowork on 2026-10-25 from `main` at `2a6f97e` (merge #128). Gate: **G3**.

## Goal, and what the video shows

Run Guideword and two one-prompt baselines on the sealed held-out accidents under rules fixed
**before anything is opened**, score them blind, and publish a results table generated from run
records: hits out of n with a 95% interval per configuration, cost, time, coverage, every failure
and every excluded case listed. The video's "numbers" beat (PROJECT.md §14, ≈40 s) and the README's
results section come only from that table.

What this phase must protect: the benchmark is the one claim no competitor makes. It is worth
something only if a sceptical reader can check that nothing was chosen, tuned or re-run after the
results were known. Every rule below exists for that reason.

## What exists today (checked on `main`, 2a6f97e)

- **The cases.** 8 held-out cases, K–S skipping O, written by a separate Claude session on
  2026-10-13 22:20 ET (decisions 2026-10-15), in `D:\Hackathon\guideword\guideword-heldout`,
  each file sealed by SHA-256 in that folder's `SEALS.txt`. Format per `docs/case-template.md`:
  a package `case_<letter>_<name>.md`, a plant file (template §3), and one key per case in
  `keys/answer_keys.json` with `case_id, root_cause, component_ids, cause_ids, match_phrases,
  consequence, missed_by_original_review, multi_failure, source`. **Nobody in this repo has
  verified that the folder actually holds plant files or keys in that shape.**
- **The seals were never committed.** `bench/heldout-seals.txt` is named in PROJECT.md §13 and
  §18 and in `specs/phase-2-plan.md` line 118, but `git log --all` has no such file. The seal date
  can therefore only be shown from the private repo's commit history or the files themselves.
  P6-1 deals with this.
- **Budget.** `benchmark` $5.19, phase cap "6" $5.19 (decisions 2026-10-25). Run rule already
  fixed: cases in sealed order, stop when the benchmark's remaining amount is under $1.30.
  Laptop total left ≈ $7.22; `development` keeps $0.93.
- **Run path.** `scripts/run_case.py` uploads a plant, confirms the **rule cut with no Super
  suggestions** ($0), starts and drives the run. Its `--use` choices are
  `development, test_5, video`: **`benchmark` is not offered**. Evidence is off for `benchmark`
  and `test_5` (P4-7). Defaults: run cap $1.00, post cap $0.30.
- **Cost reference: what counts against the run cap** (`cap_spent_usd` in `bench/phase4/`):
  D $0.99 (cap $1.20), F $0.94 (cap $2.00), G $0.76 (cap $1.40), E $1.66 (cap $2.00, after
  stopping once at the severity reserve with 186 questions open). Post-analysis spend was
  $0.12–0.16 each. The analysis stops at the cap **minus the severity reserve** (R38), so
  **at today's $1.00 default, a D-sized case would very likely stop with questions open**. P6-7
  sets the cap from these numbers.
- **Run IDs hash every routing job, prompt and `max_tokens` entry** (`runs/case.py`
  `run_settings`), except the post-step ones. Adding the probe and baseline jobs to
  `routing.yaml` (which the config loader requires) would move every new Guideword run's ID, and
  any later prompt change would move it again, so a crashed run would start a new paid run
  instead of resuming. P6-13 deals with this.
- **`bench/heldout/` is git-ignored** (`.gitignore`, CLAUDE.md §7), and CLAUDE.md §5 forbids
  Claude Code from reading it. Everything written there before G3 stays local.
- **Precedent for the probe:** kill test #4 recorded a probe (`bench/test5/kill4/run-*.jsonl`,
  fields `probe` and `recognized_incident`); on case D Ultra named a specific accident while
  marked "not recognised". P6-5's judging rule goes by what the probe named, not by its yes/no.
- **Baselines.** `bench/test5a.py` runs 5A (one Ultra call, package text + checklist,
  `prompts/test5a/v1.md`, ten ranked hazards); it reads packages only from `cases/dev/source/`.
  Kill test #4 ("plant only, no hints") has results in `bench/test5/kill4/` but **its prompt is
  not in the repo**. PROJECT.md §13's "baseline 2 = plain checklist with no reasoning" has no
  code and no prompt. P6-4 deals with this.
- **Memorisation probe.** Not built (PROJECT.md §13 says Phase 6). The dev keys carry
  `memorization_markers`; the held-out key template does not.
- **Scoring.** `bench/scoring.py` matches dev keys' `match` **groups** (every group must hit);
  the held-out template has a flat `match_phrases` list plus `component_ids` and `cause_ids`, so
  the current scorer cannot read a held-out key. `bench/results.py` renders `results.md` and the
  hand sheet (`case,config,rank,text,question_id,component_ids,score,reason`); it has **no
  confidence interval and no paired comparison**. Hand scoring so far showed the grader each
  config's lines with the config named (not blind).
- **Hit rule** (G2 and G2b, decisions 2026-10-16): a **hit** is the right mechanism on the right
  component, so an engineer reading the line would say "that's the incident"; partial is recorded
  and never counts; only top 3 passes.

## Decisions this spec asks Bhargavi to make (recommended answers given)

| # | Decision | Recommendation |
|---|---|---|
| P6-1 | **Sealing, now that the seals were never committed.** | Before the folder is opened: commit `SEALS.txt` as `bench/heldout-seals.txt`, and record in decisions.md the evidence of its date (the private repo's first commit date and hash, or the files' timestamps), stated as exactly what it is. A script then checks every file against the seals; **any mismatch stops Phase 6** until you decide. The README states the honour system and this gap plainly. |
| P6-2 | **Freeze.** | Tag `phase6-freeze` on `main` before the folder is opened. From then until G3: no change to `prompts/`, `config/routing.yaml`, the hashed `run:` block of `caps.yaml`, `reference/`, or any pipeline code. Phase 6 code (runner, probe, scorer, results) may change, since it can't change an answer. Every run records the freeze commit. A pipeline fix after the freeze makes later runs "post-freeze", reported separately and never in the headline. **Worktree rule (Bhargavi, 2026-10-25, plan G2):** every benchmark call runs from a worktree at `phase6-freeze`, and the scripts refuse anything but a clean `phase6-freeze*` checkout, so later merges to `main` can't reach a run. A post-freeze tooling fix needs a new tag that passes `scripts/check_freeze_diff.py`: only `backend/guideword/bench/` and `scripts/` may change (`api/` and `export/` may not). |
| P6-3 | **Who may read what, and when.** | Claude Code never opens the folder, as now (CLAUDE.md §5 unchanged until G3); it builds and tests every script on synthetic folders. Bhargavi runs the scripts. Order: (1) `SEALS.txt` copied and committed, then every file verified; (2) plant files validated and frozen (their hashes committed), **before anyone reads a key**; (3) probe; (3b) the probe judgement script prints, per case, the probe's answer next to **only** the key's `source` field, and Bhargavi records exclusions; (4) runs; (5) auto-score; (6) only then is the rest of the key read, for the human score. Knowing the accident's name from step 3b can't change a run, because plant files and pipeline are frozen by then. Claude Code's §5 rule is lifted only by a separate PR after G3 (P6-14). |
| P6-4 | **The baselines.** | PROJECT.md §13 names "baseline 1 = one big prompt" and "baseline 2 = plain checklist with no reasoning"; neither has a prompt in the repo. Replace them explicitly: **Baseline A = 5A as it is** (one Ultra call, package + checklist, `prompts/test5a/v1.md`), the G2b comparator, closest to §13's "checklist". **Baseline B = one Ultra call, package only, no checklist** (the kill-test #4 setup, §13's "one big prompt"): new prompt `prompts/baseline_plain/v1.md`, same output schema as 5A, drafted by Claude Code, reviewed by you. A decisions row records the replacement. About $0.02 each per case. |
| P6-5 | **The memorisation probe.** | One Ultra call per case on the package text: "is this a real accident you recognise? If so name the company, site and year, or say no", with a reason. Ultra is the model that reads the whole plant in all three configurations (plant_screen and connector in Guideword; A and B). A case is **excluded from every configuration** when the probe names the company, the site or the specific accident correctly, **whatever its own yes/no says** (kill test #4, case D), judged by you at step 3b. Probe all 8 first (about $0.04), so a recognised case costs no run. This departs from §13's "excluded for that model": since all three configurations rest on Ultra, one exclusion covers all three (decisions row). Super and Lightning are not probed; they see only slices of the plant (stated as a limit). |
| P6-6 | **A run that stops at a cap.** | Counted as a **miss** in x of n, listed as "stopped at cap: N questions open", and its partial shortlist still auto-scored and shown. No resume and no cap raise inside Phase 6. This **supersedes R38's "reported, not scored"** for the benchmark (decisions row): leaving it out would let cost choose the denominator. |
| P6-7 | **Caps and the stop rule, made exact.** | **Run cap $1.40, post cap $0.30**, set from dev analysis spend (D $0.99, F $0.94, G $0.76) plus the severity reserve; an E-sized case may still stop and counts per P6-6. Per case: baseline A, baseline B, then Guideword. Before starting a case: if benchmark remaining is under **$1.75** ($1.40 + $0.30 + $0.05 for both baselines), stop. This replaces row 2026-10-25's $1.30. Expected ≈ $1.05–1.15 a case, so ≈ 4 cases on $5.19 (worst case 2). Unrun cases are listed by letter. **If the second $25 grant lands before the first run**, raise `benchmark` (and the laptop and global totals, which must sum, `caps.yaml`) and run all unrecognised cases under the same rule; after the first run, nothing changes. |
| P6-8 | **Sealed order.** | Case letter order K, L, M, N, P, Q, R, S, skipping recognised cases. Not chosen by reading anything. |
| P6-9 | **Automatic score for the held-out key shape.** | Supersedes R26's "IDs are never matched" for held-out keys only (the template defines `component_ids` as plant-file IDs; decisions row). Any ID rename made under P6-12 is applied to the key's `component_ids` through `fixes.md`'s map at scoring time. A line auto-matches when it names at least one of the key's `component_ids` (as a failing component, chain link or, for baselines, in `equipment` or text) **and** contains at least one `match_phrases` entry after the existing normalisation. Reported as "automatic", never the headline. Also reported, auto only: **found anywhere**, the first matching rank in Guideword's full ranked list (the coverage claim), next to the top-10 result. If the keys don't have the template's fields, the scorer stops and lists the field names it found (never values) for a spec amendment. |
| P6-10 | **Human score, blind.** | One sheet per case: each configuration's top 10 lines, labelled X / Y / Z in an order fixed by `h(case_id)` (the mapping is written to a separate file and opened only after grading), every line rendered the same way: plain text plus the equipment's tag names. Guideword's record keys are swapped for names and its tier labels removed, so the grader can't tell configurations apart. Hit rule unchanged (G2/G2b): hit / partial / miss with a reason, top 3 passes. **Two graders:** you, and a fresh Claude session given only the key's `root_cause`, `component_ids`, `missed_by_original_review` and the three blind lists (the G2b fallback, used here as a second grader). Agreement is reported; disagreements are listed; **your score is the headline**, as PROJECT.md §13 says. |
| P6-11 | **Statistics, fixed now.** | Per configuration: hits in top 3 out of n, with a **Wilson 95% interval**; top 10 the same; partials shown, never counted. Paired: a per-case table of the three configurations, and an exact McNemar test (two-sided binomial on discordant cases) for Guideword vs A and Guideword vs B, with the plain sentence that the exact test needs **at least 6 discordant cases, all one way,** to reach p < 0.05, so with n ≤ 5 it cannot show a difference at all. No percentages without "x of n". No claim of "better" unless p < 0.05. Dev-case results (D–G) are shown in a separate table, labelled development, never pooled. |
| P6-12 | **Plant files that don't validate.** | Only mechanical fixes (an ID pattern, a reference to a misspelled ID that exists, a field name), each listed in `bench/heldout/fixes.md` with before and after. No fact is added, changed or removed; a fact the schema can't hold goes to `notes` verbatim. If the folder has packages but no plant files, conversion follows the dev-case rules (`cases/dev/conversion-report.md`), done by a **fresh Claude session in the held-out folder** given only `docs/case-template.md` §3 and the plant schema, told never to open `keys/` and to keep every ID the package uses, with your ticks on any assumption. All of this is finished and hashed before the probe. |
| P6-13 | **Keep the new jobs out of the run hash.** | `probe` and `baseline_plain` (job, prompt and `max_tokens`) go in a hash-free set like the post-step one, in the first PR, **before the freeze**, with a test that `run_settings` is identical with and without them. Their `routing.yaml` `jobs:` and `prompts:` entries and `caps.yaml` `max_tokens` entries land in the same PR. |
| P6-14 | **Lifting CLAUDE.md §5 after G3.** | A separate small PR, right after the G3 tag and before the publish PR, changes §5 to "published after G3". Until it merges, Bhargavi copies the files and runs the seal test herself. |
| P6-15 | **Where pre-G3 outputs live.** | Everything under `bench/heldout/` stays local and git-ignored until the publish PR. After each step, Bhargavi commits the outputs into the **private** held-out repo, which also time-stamps them. `results.md` enters this repo only in the publish PR. |

## In scope

### 6.1 Sealing and freeze (`scripts/heldout_verify.py`)
- `heldout_verify.py <folder>`: reads `SEALS.txt`, recomputes SHA-256 for every listed file,
  reports listed-but-missing, present-but-unlisted, and mismatches; exit code non-zero on any.
  Prints file names and counts only, never contents.
- Inventory: number of packages, plant files, keys; the key file's field names (not values).
- Plant validation: each plant file through `guideword.schema.plant`; errors printed by ID and
  field; the frozen hashes of the plant files written to `bench/heldout-frozen.txt` (committed).
- Bhargavi commits `bench/heldout-seals.txt` (P6-1) and tags `phase6-freeze` (P6-2).

### 6.2 Probe (`bench/probe.py`, `scripts/probe_heldout.py`, `prompts/probe/v1.md`)
- One gateway call per case (job `probe`, routed to Ultra, `max_tokens` in `caps.yaml`), outside
  any run like 5A (R9): ledger line with use `benchmark`, raw request and response to
  `bench/heldout/raw/probe/`. Output schema: `{recognised: bool, company, site, year,
  accident_name, reason}`, all strings optional, reason required.
- `bench/heldout/probe_judgement.csv`: `case, recognised_by_probe, excluded, reason`, filled by
  Bhargavi under P6-5; the runner reads it and refuses a case with no row.

### 6.3 Baselines (`bench/test5a.py` generalised, `prompts/baseline_plain/v1.md`)
- `package_for` and `run_5a` already take the folder and output root; `scripts/run_test5a.py`
  hard-codes them and its `--use` omits `benchmark`: both fixed. `JOB` and the `5a/` output
  folder become parameters, so held-out outputs land under `bench/heldout/` and never in
  `bench/test5/`.
- Baseline B: same call path, schema and validator as 5A; new job `baseline_plain` on Ultra,
  hash-free per P6-13.

### 6.4 Runner (`scripts/run_benchmark.py`)
- Inputs: the held-out folder path (argument, never a setting with a default), `--phase 6`, the
  store (`guideword-benchmark.db`; `guideword.db` and `guideword-demo.db` refused by name), the
  main checkout's ledger and `bench/heldout-frozen.txt` (plan G1, G2a, G13).
- Runs only from a clean `phase6-freeze*` worktree, with the package imported from that worktree
  (P6-2's worktree rule; plan G2b, G2c).
- For each case in P6-8 order, skipping excluded ones: check the stop rule (P6-7); run A, B, then
  Guideword through `run_case`'s functions with use `benchmark`, run cap and post cap from
  `caps.yaml`, evidence off; write each result under `bench/heldout/<case>/`; append one line per
  case to `bench/heldout/runs.jsonl` (case, config, run ID or call IDs, status, cost, seconds,
  freeze commit, questions open). A **"started" line with the run ID is written before the run
  is driven**, and before starting, the runner looks the case's run up in the store: a finished,
  cancelled or failed run would otherwise start a new paid attempt (`:<n>`). Never re-runs a
  case that has a line; a crashed case resumes its own run ID (cached calls cost $0).
- Output dir passed explicitly (`run_case`'s default is `bench/test5/5b`).
- `run_case.py`: `benchmark` added to its `--use` choices.
- A Guideword run that stops at a cap is recorded as such (P6-6) and the runner moves on.

### 6.5 Scoring (`bench/scoring.py` extended, `bench/heldout_sheet.py`, `bench/heldout_results.py`)
- Key loader for the template shape (P6-9), validating fields with a Pydantic model; the dev
  `match`-group loader is untouched.
- Auto-score per config: first matching rank, bucket, and Guideword's found-anywhere rank.
- Blind sheets (P6-10): `bench/heldout/sheets/<case>.csv` with columns
  `case,label,rank,text,equipment,score,reason`, and `bench/heldout/blind_map.json`; the results
  script joins them only when every row of every sheet has a score.
- Second-grader packet: one Markdown file per case holding only the fields P6-10 names and the
  three blind lists; its scores go in `bench/heldout/sheets_grader2/`.
- `bench/heldout/results.md`, generated, never hand-edited: the P6-11 tables; per case: probe
  result, configs, auto and hand rank, status, cost, time, coverage (checked / total and
  unsure count, from the run's coverage report); excluded and unrun cases with reasons; grader
  agreement and disagreements; total paid.

### 6.6 Publication after G3
- After `results.md` is committed: packages, plant files, keys, `SEALS.txt`, probe outputs and
  the run dumps of every held-out run go into the repo under `cases/heldout/` and
  `bench/heldout/`; the `.gitignore` line for `bench/heldout/` is removed in the same PR, and
  CLAUDE.md §5 is updated to say the cases are published. A test checks every published case
  file against `bench/heldout-seals.txt`.
- README: a results section that embeds `results.md`'s headline table and links the rest, the
  honour-system statement, the seal gap (P6-1), the frozen commit, and the limits (small n, Ultra
  probe only, one grader is the builder).

### 6.7 Docs
- PROJECT.md §13 (baselines, probe, statistics, two graders), §15 (Phase 6 and G3 dates),
  CLAUDE.md §5 (the order in P6-3; publication after G3); decisions rows for P6-1…P6-12.

## Not in scope
- Any change to the pipeline, prompts (other than the two new ones), routing or reference data.
- Evidence on benchmark runs (P4-7 stands).
- Re-running a scored case, raising a cap mid-phase, choosing which cases to run.
- The four-tier comparison on held-out cases; hosted runs; the UI for benchmark results (the
  README and `results.md` are the surface; a frontend page is "next" unless Phase 5 has slack).

## Acceptance tests (all $0, synthetic folders, written first)
1. `heldout_verify` passes a synthetic sealed folder and fails on one changed byte, one missing
   file and one unlisted file, printing names only.
2. The runner refuses a case with no probe row; skips excluded cases; follows P6-8 order; stops
   exactly when remaining < $1.75 and lists the unrun cases; never starts a second run for a
   case with a "started" line, including one whose run finished before the crash; records the
   freeze commit.
2b. `run_settings` is identical with and without the `probe` and `baseline_plain` entries
   (P6-13); a Guideword run ID is unchanged by them.
3. `run_case.py --use benchmark` runs with evidence off (the step summary says so).
4. Probe and baselines write under `bench/heldout/`, never `bench/test5/`, with ledger use
   `benchmark` and phase 6.
5. The template key loader accepts the template's example key and refuses a key missing a field,
   naming the field only.
6. Auto-score: a line with a key component and a phrase matches; a component without a phrase
   doesn't; a phrase without a component doesn't; hyphen and Unicode-dash variants match;
   found-anywhere returns the first rank in the full list.
7. Blind sheets: the X/Y/Z order is fixed by `h(case_id)`; no line text contains a record key,
   a tier label or a configuration name; regenerating gives the same files.
8. Results: Wilson interval and exact McNemar p match Cowork's hand-worked values in
   `bench/example_stats.json` (supplied with this spec; outside the ignored `bench/heldout/`):
   Wilson for 0/4, 2/4, 4/4, 3/8; McNemar for (0,0), (1,0), (3,0), (5,0), (6,0), (4,1), at a
   relative tolerance of 1e-9; a stopped run counts as a
   miss; percentages never appear without "x of n"; results refuse to render while any sheet
   row is unscored.

## Pull requests, in order (the plan may refine)
1. `phase-6/verify` — 6.1 and acceptance 1.
2. `phase-6/probe-baselines` — 6.2, 6.3, P6-13, the two prompts (drafted for your review),
   acceptance 2b and 4. Must merge **before** the freeze tag.
3. `phase-6/runner` — 6.4, acceptance 2–3.
4. `phase-6/scoring` — 6.5, acceptance 5–8.
5. `docs/heldout-published` — CLAUDE.md §5 only (P6-14), after G3.
6. `phase-6/publish` — 6.6 and 6.7.

This is backend work: the backend session builds it, so the Phase 5 frontend work (R3, R4,
F3–F6) carries on in parallel in the frontend session.

## Live calls and spend (Bhargavi starts each one)
| Step | Cost |
|---|---|
| Probe, 8 cases on Ultra | ≈ $0.04 |
| Per unrecognised case: baseline A + B | ≈ $0.04 |
| Per unrecognised case: Guideword | ≈ $0.90–1.15 typical (dev analysis $0.76–0.99 + post $0.12–0.16), $1.70 at most |
| **Total** | at most $5.19 (phase cap "6"); ≈ 4 cases on today's allowance, all 8 with the second grant |
| Second grader | a Claude session, $0 of Token Factory credit |

## Done when
- [x] Seals committed, verified with no mismatch; `phase6-freeze` tagged (runs from `phase6-freeze-3`); plant files frozen and
      hashed before any key was read.
- [x] Probe run on all 8; exclusions recorded with reasons (L, N).
- [x] Every case the stop rule allows run under all three configurations (K, M, P); unrun cases listed (Q by the stop rule, later run post-fix; R, S not converted).
- [x] Auto-scored; both graders done blind; `results.md` generated (committed here under `bench/heldout/`, not to the private repo, which holds the cases only).
- [x] §5 updated in the publish PR (P6-14 folded in); cases, keys, run dumps and `results.md` published; README results
      section live. G3 tag: Bhargavi tags `g3` on `main` after the publish PR merges.
- [x] Decisions rows for P6-1…P6-15 (including R26, R38 and §13 supersessions); PROJECT.md and
      CLAUDE.md updated.

## Who writes what
- **Claude Code:** every script and test in 6.1–6.5, the two prompt drafts, the publish PR.
- **Bhargavi:** approves this spec and the plan; reviews the two prompts; commits the seals; tags
  the freeze; runs every script and paid call; judges the probe; grades blind; decides any
  mismatch or validation stop.
- **Cowork:** `bench/example_stats.json` (hand-worked Wilson and McNemar values, done); the
  second-grader instructions; a review of `results.md` and the README text against
  the records. Cowork does not propose scores.

## Dates (PROJECT.md §15 rule: not working by its date → said plainly in the pitch)
| Date | Step |
|---|---|
| Oct 25 | Spec approved; seals committed; plan written |
| Oct 26 | PRs 1–4 merged; prompts reviewed; freeze tagged; folder opened and verified; plant files frozen |
| Oct 27 | Probe; runs in sealed order |
| Oct 27–28 | Auto-score; blind grading by both graders; `results.md` |
| Oct 28 | G3 tagged; publish PR; README results; video's numbers beat recorded |
