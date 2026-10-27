"""The memorisation probe and its judgement (Phase 6 spec 6.2, P6-5, P6-3 step 3b; plan G7).

**The probe.** One Ultra call per held-out case on the package text (`prompts/probe/`), outside
any run like 5A (R9): through the gateway (cache, budget guard, ledger line with use
`benchmark`), its raw request and response to `<root>/raw/probe/`, its answer to
`<root>/probe/`. A cut-off or invalid answer is a failure, never parsed.

**The judgement** (step 3b). For each probed case, the probe's answer is shown next to **only**
the key's `source` field: each key record is read into a model that keeps `case_id` and
`source` and drops every other field unread. `probe_judgement.csv` is written once, with the
probe's yes/no, for Bhargavi to fill `excluded` and `reason`; the runner reads it back and
refuses a case whose row is missing or unfilled. A case is excluded when the probe names the
company, the site or the accident correctly, whatever its own `recognised` says (P6-5).
"""

import csv
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, StringConstraints

from guideword.bench.heldout_keys import key_records
from guideword.bench.scoring import case_letter
from guideword.bench.test5a import package_for
from guideword.config import Config
from guideword.gateway.client import Gateway, RunBudget
from guideword.gateway.prompts import load_prompt, render

JOB = "probe"
FOLDER = "probe"
ASK = "Answer the question in the required JSON schema."
COLUMNS = ("case", "recognised_by_probe", "excluded", "reason")
YES_NO = {"yes": True, "no": False}

Text = Annotated[str, StringConstraints(min_length=1, max_length=300)]
Name = Annotated[str, StringConstraints(max_length=200)]


class ProbeAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recognised: bool
    company: Name | None = None
    site: Name | None = None
    year: Annotated[str, StringConstraints(max_length=20)] | None = None
    accident_name: Name | None = None
    reason: Text


class _KeySource(BaseModel):
    """A key record as step 3b may read it: its case and its source, nothing else."""

    model_config = ConfigDict(extra="ignore")

    case_id: str
    # the template gives an object (kind, reference, pages); a plain string is accepted too
    source: Any


class JudgementRefused(ValueError):
    """The judgement file is missing a case, unfilled, unclear, or would be overwritten."""


@dataclass(frozen=True)
class JudgementRow:
    case: str
    probe: dict[str, Any] | None
    source: Any


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )


def run_probe(
    gateway: Gateway, config: Config, letter: str, *, source_dir: Path, out_root: Path
) -> dict[str, Any]:
    package = package_for(letter, source_dir)
    prompt = load_prompt(JOB, config)
    text = package.read_text(encoding="utf-8").rstrip("\n")
    if "<package>" in text or "</package>" in text:
        raise ValueError(f"{package.name} holds a <package> tag; it cannot be sent as data")
    messages = [
        {"role": "system", "content": render(prompt.body, {"package": text})},
        {"role": "user", "content": ASK},
    ]
    result = gateway.call(
        job=JOB,
        prompt_version=prompt.label,
        messages=messages,
        schema=ProbeAnswer,
        # a per-call limit, though no run is stored (R9)
        run=RunBudget(f"run:{JOB}-{letter}", 0.0, config.caps.run.run_spend_cap_usd),
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
        "model_call_ids": [c.id for c in result.model_calls],
        "answer": answer.model_dump() if isinstance(answer, ProbeAnswer) else None,
    }
    _write(out_root / FOLDER / f"case_{letter}.json", record)
    _write(
        out_root / "raw" / FOLDER / f"case_{letter}.json",
        {
            "request": {"job": JOB, "prompt_version": prompt.label, "messages": messages},
            "calls": [
                c.model_dump(mode="json", exclude={"run_id", "record_ids"})
                for c in result.model_calls
            ],
        },
    )
    return record


def _key_sources(keys_path: Path) -> dict[str, Any]:
    """Case letter -> the key's `source`, from a keys file or a keys folder; nothing else."""
    sources: dict[str, Any] = {}
    for record in key_records(keys_path):
        key = _KeySource.model_validate(record)
        sources[case_letter(f"case_{key.case_id.lower().removeprefix('case_')}")] = key.source
    return sources


def judgement_rows(probe_dir: Path, keys_path: Path) -> list[JudgementRow]:
    """Each probed case's answer (None when the probe failed) beside its key's source."""
    sources = _key_sources(keys_path)
    rows = []
    for path in sorted(probe_dir.glob("case_*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        letter = case_letter(record["case"])
        rows.append(JudgementRow(letter, record.get("answer"), sources.get(letter)))
    return rows


def write_judgement(rows: Iterable[JudgementRow], path: Path) -> None:
    """The CSV Bhargavi fills; written once, so a filled file is never overwritten."""
    if path.exists():
        raise JudgementRefused(f"{path} exists; the judgement is written once")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            recognised = (
                "failed" if row.probe is None else ("yes" if row.probe["recognised"] else "no")
            )
            writer.writerow(
                {"case": row.case, "recognised_by_probe": recognised, "excluded": "", "reason": ""}
            )


def read_judgement(path: Path) -> dict[str, bool]:
    """Case letter -> excluded. Every row must say yes or no, with a reason when excluded."""
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    out: dict[str, bool] = {}
    for row in rows:
        case = (row.get("case") or "").strip().lower()
        excluded = (row.get("excluded") or "").strip().lower()
        if excluded not in YES_NO:
            raise JudgementRefused(f"case {case}: excluded must be yes or no")
        if YES_NO[excluded] and not (row.get("reason") or "").strip():
            raise JudgementRefused(f"case {case}: an excluded case needs a reason")
        out[case] = YES_NO[excluded]
    return out
