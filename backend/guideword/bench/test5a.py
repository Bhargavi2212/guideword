"""Test #5A (spec 2.10; plan R9): the baseline. One Ultra call per dev case with the package
text and a step-by-step checklist (`prompts/test5a/`), answered with ten ranked hazards.

Outside any run, so no `ModelCall` is stored: the call goes through the gateway (cache,
budget guard, ledger line) and its raw request and response are written to
`<root>/raw/5a/case_<letter>.json`; the ranked hazards to `<root>/5a/` (`bench/test5/` for the
dev cases).

Phase 6 (spec 6.3, P6-4): the same call path runs both held-out baselines. **Baseline A** is 5A
as it is; **baseline B** (`baseline_plain`) is the package with no checklist, with 5A's schema and
validator, into its own folder. The root is the caller's, so held-out outputs land under
`bench/heldout/`, never `bench/test5/`.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from guideword.config import Config
from guideword.gateway.client import Gateway, RunBudget
from guideword.gateway.prompts import load_prompt, render

JOB = "test5a"
MAX_HAZARDS = 10
ANSWER_FILE = "case_{letter}.json"
RAW_DIR = Path("raw") / "5a"
ASK = "Work through the checklist and answer with the ranked hazards, in the required JSON schema."

Text = Annotated[str, StringConstraints(min_length=1, max_length=300)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Hazard(_Strict):
    rank: Annotated[int, Field(ge=1)]
    hazard: Text
    equipment: list[str]
    reason: Text


class Test5AAnswer(_Strict):
    hazards: Annotated[list[Hazard], Field(min_length=1, max_length=MAX_HAZARDS)]


def _ranks_in_order(value: Any) -> None:
    if not isinstance(value, Test5AAnswer):
        raise ValueError("not a 5A answer")
    ranks = [h.rank for h in value.hazards]
    if ranks != list(range(1, len(ranks) + 1)):
        raise ValueError(f"hazards must be ranked 1 to {len(ranks)} in order, got rank {ranks}")


@dataclass(frozen=True)
class Baseline:
    """A one-call baseline: its routing job (and prompt) and the folder its answers go in."""

    job: str
    folder: str


BASELINE_A = Baseline(JOB, "5a")
BASELINE_B = Baseline("baseline_plain", "baseline_b")


def package_for(letter: str, source_dir: Path) -> Path:
    """The one package `case_<letter>_*.md` in the dev sources."""
    found = sorted(source_dir.glob(f"case_{letter}_*.md"))
    if len(found) != 1:
        raise LookupError(
            f"expected one package for case {letter} in {source_dir}, found {len(found)}"
        )
    return found[0]


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )


def run_5a(
    gateway: Gateway, config: Config, letter: str, *, source_dir: Path, out_root: Path
) -> dict[str, Any]:
    return run_baseline(
        gateway, config, letter, baseline=BASELINE_A, source_dir=source_dir, out_root=out_root
    )


def run_baseline(
    gateway: Gateway,
    config: Config,
    letter: str,
    *,
    baseline: Baseline,
    source_dir: Path,
    out_root: Path,
) -> dict[str, Any]:
    job = baseline.job
    package = package_for(letter, source_dir)
    prompt = load_prompt(job, config)
    text = package.read_text(encoding="utf-8").rstrip("\n")
    # kept as written, so 5A on E and F reads what it read on D and G (G22): a package that
    # could open or close its block is refused instead of escaped
    if "<package>" in text or "</package>" in text:
        raise ValueError(f"{package.name} holds a <package> tag; it cannot be sent as data")
    system = render(prompt.body, {"package": text})
    messages = [{"role": "system", "content": system}, {"role": "user", "content": ASK}]
    result = gateway.call(
        job=job,
        prompt_version=prompt.label,
        messages=messages,
        schema=Test5AAnswer,
        validator=_ranks_in_order,
        # a per-call limit: the run cap, though no run is stored (R9)
        run=RunBudget(f"run:{job}-{letter}", 0.0, config.caps.run.run_spend_cap_usd),
    )
    answer = result.value if result.outcome == "ok" else None
    record = {
        "case": f"case_{letter}",
        "package": package.name,
        "model_id": result.model_id,
        "prompt_version": prompt.label,
        "outcome": result.outcome,
        "error": result.error,
        "cost_usd": result.cost_usd,
        "cache_hit": result.cache_hit,
        "seconds": sum(c.latency_ms for c in result.model_calls) / 1000,
        "hazards": [h.model_dump() for h in answer.hazards] if answer is not None else [],
    }
    _write(out_root / baseline.folder / ANSWER_FILE.format(letter=letter), record)
    _write(
        out_root / "raw" / baseline.folder / f"case_{letter}.json",
        {
            "request": {"job": job, "prompt_version": prompt.label, "messages": messages},
            "calls": [
                c.model_dump(mode="json", exclude={"run_id", "record_ids"})
                for c in result.model_calls
            ],
        },
    )
    return record
