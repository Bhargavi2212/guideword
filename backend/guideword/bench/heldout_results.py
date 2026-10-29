"""`results.md`, generated from the run records and never edited by hand (Phase 6 spec 6.5, P6-6,
P6-10, P6-11; acceptance 8).

Reads `<out>/`: `runs.jsonl`, `not_converted.json` (when the runner wrote one),
`probe_judgement.csv`, `auto_scores.json`, both graders' sheets (`sheets/`, `sheets_grader2/`),
`blind_map.json` and each case's `guideword.json`. It refuses to render while any row of any sheet
has no score (hit, partial or miss).

- **Headline** (Bhargavi's score, as PROJECT.md §13 says): per configuration, hits in the top 3
  out of n, with a Wilson interval at 0.95; the top 10 the same; partials shown, never counted. A
  Guideword run that stopped at its cap counts as a miss (P6-6). Proportions are written as
  "x of n" and intervals as decimals, never percentages.
- **Paired**: per case, the three configurations; the exact McNemar test for Guideword against
  each baseline, with the sentence saying how many discordant cases it would need. No claim of
  a difference unless p < 0.05.
- **Automatic score** (not the headline), with Guideword's found-anywhere rank.
- **Per case**: probe, status, cost, time, coverage; excluded and unrun cases with reasons;
  grader agreement and every disagreement; total paid.
- **Development cases** (D–G): a link to `bench/test5/results.md`, as recorded, never pooled.
"""

import csv
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from guideword.bench.runner import CONFIGS, NOT_CONVERTED_FILE, read_lines
from guideword.bench.scoring import bucket
from guideword.bench.stats import ALPHA, mcnemar_exact, smallest_one_way_discordant, wilson_95

NAMES = {
    "guideword": "Guideword",
    "baseline_a": "Baseline A (5A, checklist)",
    "baseline_b": "Baseline B (one prompt)",
}
SCORES = ("hit", "partial", "miss")
GRADERS = (("sheets", "Bhargavi"), ("sheets_grader2", "second grader"))
DEV_RESULTS = "[bench/test5/results.md](../../bench/test5/results.md)"


class ResultsRefused(ValueError):
    """A sheet row is unscored, or a record the results need is missing."""


def _not_converted(out: Path) -> list[str]:
    """The cases the runner found with no frozen plant file (decisions 2026-10-28)."""
    path = out / NOT_CONVERTED_FILE
    if not path.is_file():
        return []
    return sorted(json.loads(path.read_text(encoding="utf-8"))["cases"])


def _judgement(out: Path) -> dict[str, dict[str, str]]:
    with (out / "probe_judgement.csv").open(encoding="utf-8", newline="") as f:
        return {row["case"]: row for row in csv.DictReader(f)}


def _sheet(path: Path, mapping: Mapping[str, str]) -> dict[str, list[tuple[int, str]]]:
    """Config -> [(rank, score)], refusing an unscored or unknown score."""
    scores: dict[str, list[tuple[int, str]]] = {c: [] for c in CONFIGS}
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            score = row["score"].strip().lower()
            if score not in SCORES:
                raise ResultsRefused(
                    f"{path.name}: rank {row['rank']} of {row['label']} has no score"
                )
            scores[mapping[row["label"]]].append((int(row["rank"]), score))
    return scores


def _hit(rows: list[tuple[int, str]], top: int) -> bool:
    return any(score == "hit" and rank <= top for rank, score in rows)


def _partial(rows: list[tuple[int, str]], top: int) -> bool:
    return not _hit(rows, top) and any(s == "partial" and r <= top for r, s in rows)


def _interval(x: int, n: int) -> str:
    low, high = wilson_95(x, n)
    return f"{low:.2f} to {high:.2f}"


def render_results(out: Path) -> str:
    judgement = _judgement(out)
    lines = read_lines(out / "runs.jsonl")
    done = {(x["case"], x["config"]): x for x in lines if x["state"] == "done"}
    run = sorted({c for c, _ in done if all((c, k) in done for k in CONFIGS)})
    excluded = sorted(c for c, row in judgement.items() if row["excluded"].strip().lower() == "yes")
    not_converted = _not_converted(out)
    unrun = sorted(
        c for c in judgement if c not in excluded and c not in run and c not in not_converted
    )
    mapping: dict[str, dict[str, str]] = json.loads((out / "blind_map.json").read_text("utf-8"))
    graded: dict[str, dict[str, dict[str, list[tuple[int, str]]]]] = {}
    for folder, _ in GRADERS:
        graded[folder] = {}
        for case in run:
            path = out / folder / f"{case}.csv"
            if not path.is_file():
                raise ResultsRefused(f"{folder}/{case}.csv is missing")
            graded[folder][case] = _sheet(path, mapping[case])
    auto: dict[str, dict[str, Any]] = json.loads((out / "auto_scores.json").read_text("utf-8"))
    n = len(run)
    stopped = {c for c in run if done[(c, "guideword")].get("status") != "finished"}

    def hits(config: str, top: int, folder: str = "sheets") -> dict[str, bool]:
        return {
            c: _hit(graded[folder][c][config], top) and not (config == "guideword" and c in stopped)
            for c in run
        }

    first = lines[0] if lines else {}
    out_lines = [
        "# Held-out benchmark results",
        "",
        "Generated by `scripts/heldout_results.py` from the run records; never edited by hand.",
        "",
        f"- Freeze: `{first.get('freeze_tag')}` at `{first.get('freeze_commit')}`",
        f"- Cases run: {n} ({', '.join(run) or 'none'})",
        "",
        "## Headline: Bhargavi's score, the root cause in the top 3",
        "",
        "| Configuration | Top 3 | Wilson interval (0.95) | Top 10 | Wilson interval (0.95) "
        "| Partials (not counted) |",
        "|---|---|---|---|---|---|",
    ]
    for config in ("guideword", "baseline_a", "baseline_b"):
        top3 = sum(hits(config, 3).values())
        top10 = sum(hits(config, 10).values())
        partial = sum(_partial(graded["sheets"][c][config], 3) for c in run)
        cells = [f"{top3} of {n}", _interval(top3, n), f"{top10} of {n}", _interval(top10, n)]
        if n == 0:
            cells = ["0 of 0", "-", "0 of 0", "-"]
        out_lines.append(f"| {NAMES[config]} | " + " | ".join(cells) + f" | {partial} |")
    out_lines.append("")
    out_lines.append(
        "A Guideword run that stopped at its cap counts as a miss (P6-6). A partial is shown and "
        "never counted."
    )

    out_lines += [
        "",
        "## Paired, per case (top 3)",
        "",
        "| Case | Guideword | Baseline A | Baseline B |",
        "|---|---|---|---|",
    ]
    g = hits("guideword", 3)
    for c in run:
        row = [
            ("hit" if hits(k, 3)[c] else "miss") for k in ("guideword", "baseline_a", "baseline_b")
        ]
        out_lines.append(f"| {c} | " + " | ".join(row) + " |")
    needed = smallest_one_way_discordant()
    out_lines.append("")
    for other in ("baseline_a", "baseline_b"):
        o = hits(other, 3)
        b = sum(g[c] and not o[c] for c in run)
        cc = sum(o[c] and not g[c] for c in run)
        p = mcnemar_exact(b, cc)
        verdict = "a difference at p < 0.05" if p < ALPHA else "no difference is claimed"
        out_lines.append(
            f"- Guideword against {NAMES[other]}: {b} cases only Guideword found, {cc} only the "
            f"baseline found; exact McNemar p = {p:.4f}: {verdict}."
        )
    out_lines.append(
        f"- With n = {n}, the exact test needs at least {needed} discordant cases, all one way, to "
        "reach p < 0.05."
    )

    out_lines += [
        "",
        "## Automatic score (not the headline)",
        "",
        "First matching line: a key component and a key phrase in the same line (P6-9).",
        "",
        "| Case | Guideword | Baseline A | Baseline B | Guideword found anywhere |",
        "|---|---|---|---|---|",
    ]
    for c in run:
        a = auto.get(c, {})
        cells = [bucket(a.get(k)) for k in ("guideword", "baseline_a", "baseline_b")]
        anywhere = a.get("guideword_found_anywhere")
        out_lines.append(
            f"| {c} | "
            + " | ".join(cells)
            + f" | {anywhere if anywhere is not None else 'not found'} |"
        )

    out_lines += ["", "## Per case", ""]
    for c in run:
        gw = done[(c, "guideword")]
        report = json.loads((out / f"case_{c}" / "guideword.json").read_text(encoding="utf-8"))
        checked = sum(x["checked"] for x in report.get("coverage", []))
        total = sum(x["total"] for x in report.get("coverage", []))
        unsure = sum(x["unsure"] for x in report.get("coverage", []))
        status = gw.get("status")
        if status != "finished":
            status = f"stopped at cap: {gw.get('questions_open')} questions open"
        cost = sum(float(done[(c, k)].get("cost_usd") or 0) for k in CONFIGS)
        seconds = sum(float(done[(c, k)].get("seconds") or 0) for k in CONFIGS)
        probe = judgement[c]["recognised_by_probe"]
        out_lines.append(
            f"- {c}: Guideword {status}; coverage {checked} / {total} checked, {unsure} unsure; "
            f"probe recognised: {probe}; cost ${cost:.2f}; time {seconds:.0f} s"
        )
    out_lines += ["", "Excluded by the probe (P6-5):"]
    out_lines += [f"- {c}: {judgement[c]['reason']}" for c in excluded] or ["- none"]
    out_lines += ["", "Not run:"]
    out_lines += [f"- {c}: not run (stop rule)" for c in unrun] + [
        f"- {c}: not converted: not run" for c in not_converted
    ] or ["- none"]

    agree, calls = 0, 0
    disagreements: list[str] = []
    for c in run:
        for config in ("guideword", "baseline_a", "baseline_b"):
            one = _hit(graded["sheets"][c][config], 3)
            two = _hit(graded["sheets_grader2"][c][config], 3)
            calls += 1
            agree += one == two
            if one != two:
                disagreements.append(
                    f"- {c}, {NAMES[config]}: Bhargavi {'hit' if one else 'miss'}, second grader "
                    f"{'hit' if two else 'miss'}"
                )
    out_lines += [
        "",
        "## Graders",
        "",
        f"Graders agree on {agree} of {calls} top-3 calls; Bhargavi's score is the headline.",
        *disagreements,
    ]
    paid = sum(float(x.get("cost_usd") or 0) for x in done.values())
    out_lines += [
        "",
        "## Development cases (D–G)",
        "",
        "Shown separately, as recorded, by configuration as stored, and never pooled: "
        f"{DEV_RESULTS} (development).",
        "",
        f"Total paid: ${paid:.2f}",
        "",
    ]
    return "\n".join(out_lines)
