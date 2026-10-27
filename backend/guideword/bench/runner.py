"""The held-out runner (Phase 6 spec 6.4, P6-6, P6-7, P6-8; plan G1, G13, G14; acceptance 2, 3).

Bhargavi runs `scripts/run_benchmark.py`; this module is its logic, tested on synthetic cases.

- **Which cases.** Every case in the held-out folder: a package `case_<letter>_*.md` and its plant
  file `case_<letter>*.json`, in letter order (P6-8). Each needs a row in the probe judgement;
  a case with none stops the runner before any call. Excluded cases are skipped (P6-5).
- **The plant files.** Each must match its hash in `bench/heldout-frozen.txt` (G13).
- **Per case:** baseline A, baseline B, then Guideword. Before a case starts, the stop rule
  (P6-7): if the benchmark allowance has less than `stop_below_usd` left, no further case
  starts, and the cases not run are listed by letter. A case already started is finished.
- **`runs.jsonl`**, one line per configuration and state. A Guideword run writes a `started`
  line with its run ID **before** it is driven; on a later start the runner reads that ID back
  and never starts a second run for the case: an unfinished run resumes (cached calls cost $0),
  a finished, capped, cancelled or failed one is reported as it stands. A `done` line is never
  run again. Every line names the freeze tag and commit.
- **A capped run** (P6-6) is recorded with its status, its open questions and its ranked list,
  and the runner moves on: it counts as a miss when scored.
"""

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from guideword.bench.freeze import FreezeInfo
from guideword.bench.heldout import classify, read_seals
from guideword.bench.test5a import Baseline, run_baseline
from guideword.config import Config
from guideword.evidence.step import EvidenceTools
from guideword.gateway.client import Gateway
from guideword.reference import ReferenceSet
from guideword.runs.case import case_report, drive, prepare_plant, start_case, steppers_for
from guideword.runs.plants import PlantRepository
from guideword.runs.store import RunRepository
from guideword.schema.enums import BudgetUse, RunStatus

CONFIGS = ("baseline_a", "baseline_b", "guideword")
# a run in these is driven on; any other status is reported as it stands
UNFINISHED = frozenset({RunStatus.DRAFT, RunStatus.RUNNING})
RUNS_FILE = "runs.jsonl"
_LETTER = re.compile(r"^case_([a-z])", re.IGNORECASE)


class RunnerRefused(RuntimeError):
    """The runner won't start: a case has no judgement row, or a plant file isn't frozen."""


@dataclass(frozen=True)
class Case:
    letter: str
    package: Path
    plant: Path


@dataclass
class Summary:
    run: list[str] = field(default_factory=list)
    excluded: list[str] = field(default_factory=list)
    already_done: list[str] = field(default_factory=list)
    # cases the stop rule left unrun, by letter, and the amount left when it stopped
    unrun: list[str] = field(default_factory=list)
    stopped_with_usd: float | None = None


def _letter(path: Path) -> str:
    match = _LETTER.match(path.name)
    if match is None:
        raise RunnerRefused(f"{path.name} is not a case file")
    return match.group(1).lower()


def find_cases(folder: Path) -> list[Case]:
    """Each case's package and plant file, in letter order; a case missing either is refused."""
    packages: dict[str, Path] = {}
    plants: dict[str, Path] = {}
    for path in sorted(folder.rglob("case_*")):
        if not path.is_file():
            continue
        kind = classify(path.relative_to(folder).as_posix())
        if kind == "package":
            packages.setdefault(_letter(path), path)
        elif kind == "plant":
            plants.setdefault(_letter(path), path)
    letters = sorted(set(packages) | set(plants))
    lonely = [x for x in letters if x not in packages or x not in plants]
    if lonely:
        raise RunnerRefused(f"cases without both a package and a plant file: {', '.join(lonely)}")
    return [Case(x, packages[x], plants[x]) for x in letters]


def check_frozen(folder: Path, cases: Sequence[Case], frozen: Path) -> None:
    """Every case's plant file still has the hash written when the plant files were frozen."""
    hashes, bad = read_seals(frozen.read_text(encoding="utf-8"))
    if bad:
        raise RunnerRefused(f"{frozen.name} has lines that are not hashes: {bad}")
    for case in cases:
        relative = case.plant.relative_to(folder).as_posix()
        if relative not in hashes:
            raise RunnerRefused(f"{relative} is not in {frozen.name}")
        if hashlib.sha256(case.plant.read_bytes()).hexdigest() != hashes[relative]:
            raise RunnerRefused(f"{relative} has changed since it was frozen")


def check_judgement(cases: Sequence[Case], judgement: Mapping[str, bool]) -> None:
    missing = [c.letter for c in cases if c.letter not in judgement]
    if missing:
        raise RunnerRefused(f"no probe judgement row for case {', '.join(missing)}")


def read_lines(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _append(path: Path, line: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def benchmark_remaining(entries: Sequence[Any], allowance_usd: float) -> float:
    """The benchmark allowance less what the ledger books to use `benchmark`."""
    spent = sum(float(e.cost_usd) for e in entries if str(e.use) == "benchmark")
    return float(allowance_usd) - spent


# a configuration: (case, the run ID of an earlier `started` line or None, a callback that writes
# the `started` line) -> the line's fields (status, cost_usd, seconds, run_id ...)
RunConfig = Callable[[Case, str | None, Callable[[str], None]], dict[str, Any]]


def run_benchmark(
    cases: Sequence[Case],
    *,
    judgement: Mapping[str, bool],
    configs: Mapping[str, RunConfig],
    lines_path: Path,
    remaining: Callable[[], float],
    stop_below_usd: float,
    freeze: FreezeInfo,
    after_case: Callable[[Case], None] = lambda case: None,
) -> Summary:
    check_judgement(cases, judgement)
    summary = Summary()
    stamp = {"freeze_tag": freeze.tag, "freeze_commit": freeze.commit}
    for n, case in enumerate(cases):
        if judgement[case.letter]:
            summary.excluded.append(case.letter)
            continue
        lines = [x for x in read_lines(lines_path) if x["case"] == case.letter]
        done = {x["config"] for x in lines if x["state"] == "done"}
        if done >= set(CONFIGS):
            summary.already_done.append(case.letter)
            continue
        if not lines:
            left = remaining()
            if left < stop_below_usd:
                summary.stopped_with_usd = left
                summary.unrun = [
                    c.letter
                    for c in cases[n:]
                    if not judgement[c.letter]
                    and not [x for x in read_lines(lines_path) if x["case"] == c.letter]
                ]
                break
        for name in CONFIGS:
            if name in done:
                continue
            started = [
                x["run_id"] for x in lines if x["config"] == name and x["state"] == "started"
            ]

            def mark(run_id: str, name: str = name, letter: str = case.letter) -> None:
                _append(
                    lines_path,
                    {"case": letter, "config": name, "state": "started", "run_id": run_id} | stamp,
                )

            result = configs[name](case, started[-1] if started else None, mark)
            _append(
                lines_path, {"case": case.letter, "config": name, "state": "done"} | result | stamp
            )
        summary.run.append(case.letter)
        after_case(case)
    return summary


# --- the three configurations ----------------------------------------------------------------


def baseline_config(gateway: Gateway, config: Config, baseline: Baseline, out: Path) -> RunConfig:
    """Baseline A or B on the case's package, its answer under `<out>/case_<letter>/`."""

    def run(case: Case, started: str | None, mark: Callable[[str], None]) -> dict[str, Any]:
        record = run_baseline(
            gateway,
            config,
            case.letter,
            baseline=baseline,
            source_dir=case.package.parent,
            out_root=out / f"case_{case.letter}",
        )
        return {
            "status": record["outcome"],
            "cost_usd": record["cost_usd"],
            "seconds": record["seconds"],
            "model_call_ids": record["model_call_ids"],
        }

    return run


@dataclass(frozen=True)
class GuidewordParts:
    """What a Guideword run needs: the stores, reference tables, config, gateway, tools."""

    plants: PlantRepository
    runs: RunRepository
    ref: ReferenceSet
    config: Config
    gateway: Gateway
    evidence: EvidenceTools
    # the final shortlist the product shows, as JSON items (the API's), for the scorer (P6-9)
    shortlist_of: Callable[[str], list[dict[str, Any]]]


def guideword_config(parts: GuidewordParts, out: Path) -> RunConfig:
    """Guideword on the case's plant file, with use `benchmark` and the benchmark's caps.

    A new case uploads the plant, starts the run, writes the `started` line, then drives it. A
    case with a `started` line reads its run back: it is driven only while unfinished, so a
    finished, capped, cancelled or failed run is reported as it stands and never restarted."""
    bench = parts.config.caps.benchmark

    def run(case: Case, started: str | None, mark: Callable[[str], None]) -> dict[str, Any]:
        if started is None:
            record = prepare_plant(
                parts.plants, json.loads(case.plant.read_text(encoding="utf-8")), parts.ref
            )
            begun = start_case(
                parts.plants,
                parts.runs,
                parts.ref,
                parts.config,
                record.id,
                bench.run_cap_usd,
                use=BudgetUse.BENCHMARK,
                post_spend_cap_usd=bench.post_cap_usd,
            )
            mark(begun.id)
            run_id = begun.id
        else:
            run_id = started
        stored = parts.runs.get(run_id)
        if stored is None:
            raise RunnerRefused(f"case {case.letter}: run {run_id} is not in the store")
        plant_record = parts.plants.get(stored.plant_record_id)
        if plant_record is None:
            raise RunnerRefused(f"case {case.letter}: run {run_id} has no plant")
        plant = plant_record.record.plant_file
        if stored.status in UNFINISHED:
            drive(
                parts.runs,
                run_id,
                steppers_for(
                    parts.gateway, parts.config, parts.ref, plant, evidence=parts.evidence
                ),
            )
        report = case_report(
            parts.runs, run_id, plant, parts.ref, parts.config.caps, f"case_{case.letter}"
        )
        folder = out / f"case_{case.letter}"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "guideword.json").write_text(
            json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
        )
        shortlist = {
            "run_id": run_id,
            "items": parts.shortlist_of(run_id),
            "finding_components": {
                f.id: list(f.failing_component_ids) for f in parts.runs.findings(run_id)
            },
        }
        (folder / "shortlist.json").write_text(
            json.dumps(shortlist, indent=1, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return {
            "run_id": run_id,
            "status": report["status"],
            "cost_usd": report["spent_usd"],
            "seconds": report["seconds"],
            "questions_open": report["open_questions"],
        }

    return run
