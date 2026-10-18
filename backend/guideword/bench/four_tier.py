"""The four-tier comparison (spec 2.10; plan PR 12b, R9, R27, R35).

A fixed sample of the questions of D–H, the `SAMPLE_SIZE` lowest `h([plant_id, question_id])`
(R27), each answered by its own specialist on every tier of `config/models.yaml` with each
tier's own request settings and the same prompt versions. Questions are batched by case and
agent, never mixed, at each tier's batch size, group by group with every tier in turn (so a
stop at the cap cuts all tiers alike), through the run path's `prepare_batch` and
`run_batch` with the tier forced. Recorded per tier: how many questions got a valid answer
(answered or dismissed as not credible), the median batch latency, and the cost. The calls are
outside any run (R9): a ledger line each through the gateway, no stored ModelCall; the raw
request and response go to `bench/test5/raw/four_tier/`. Hand scores (good / partial / wrong)
go in `bench/test5/four_tier_scores.csv` (R35), a blank template that keeps filled rows.
"""

import csv
import json
import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from guideword.config import Config
from guideword.gateway.client import BudgetRefused, Gateway, RunBudget
from guideword.questions.build import build_questions
from guideword.reference import ReferenceSet
from guideword.runs.case import _text
from guideword.schema import ids
from guideword.schema.enums import QuestionStatus, Tier
from guideword.schema.plant import Plant
from guideword.schema.records import Question, Section
from guideword.sections.rules import rule_cut
from guideword.specialists.batch import batches
from guideword.specialists.routing import agent_for
from guideword.specialists.run import BatchOutcome, prepare_batch, run_batch

SAMPLE_SIZE = 50  # spec 2.10
SCORES = "four_tier_scores.csv"
SCORE_FIELDS = ["question_key", "tier", "score", "reason"]  # R35
DONE = (QuestionStatus.ANSWERED, QuestionStatus.NOT_CREDIBLE)


@dataclass(frozen=True)
class SampleQuestion:
    case: str
    plant: Plant
    sections: list[Section]
    question: Question

    @property
    def key(self) -> str:
        """`<case>:<question ID>`: question IDs repeat across cases (R27)."""
        return f"{self.case}:{self.question.id}"


@dataclass
class TierResult:
    questions: int = 0
    answered: int = 0
    valid: int = 0
    cost_usd: float = 0.0
    latencies_s: list[float] = field(default_factory=list)
    answers: list[dict[str, Any]] = field(default_factory=list)
    raw: list[dict[str, Any]] = field(default_factory=list)

    @property
    def valid_rate(self) -> float:
        return self.valid / self.questions if self.questions else 0.0

    @property
    def median_latency_s(self) -> float:
        return statistics.median(self.latencies_s) if self.latencies_s else 0.0


@dataclass
class FourTierResult:
    tiers: dict[str, TierResult]
    stopped: str | None = None


def load_cases(directory: Path) -> list[tuple[str, Plant]]:
    """The dev plant files `case_<letter>.json`, as (case, plant)."""
    found = []
    for path in sorted(directory.glob("case_*.json")):
        plant = Plant.model_validate(json.loads(path.read_text(encoding="utf-8")))
        found.append((path.stem, plant))
    return found


def sample(
    cases: Sequence[tuple[str, Plant]], ref: ReferenceSet, size: int = SAMPLE_SIZE
) -> list[SampleQuestion]:
    every: list[SampleQuestion] = []
    for case, plant in cases:
        record_id = ids.plant_record_id(plant.plant_id, plant.model_dump(mode="json"))
        sections = rule_cut(plant, record_id)
        run_id = f"run:{ids.h(['four_tier', plant.plant_id])}"
        for question in build_questions(plant, sections, ref, run_id):
            every.append(SampleQuestion(case, plant, sections, question))
    every.sort(key=lambda s: (ids.h([s.plant.plant_id, s.question.id]), s.key))
    return every[:size]


def _groups(picked: Sequence[SampleQuestion]) -> list[list[SampleQuestion]]:
    """One group per case and agent, in a stable order."""
    groups: dict[tuple[str, str], list[SampleQuestion]] = {}
    for s in picked:
        agent = agent_for(s.question, {x.id: x for x in s.sections})
        groups.setdefault((s.case, agent.value), []).append(s)
    return [groups[k] for k in sorted(groups)]


def run_four_tier(
    gateway: Gateway,
    config: Config,
    ref: ReferenceSet,
    picked: Sequence[SampleQuestion],
    *,
    cap_usd: float,
    timer: Callable[[], float],
) -> FourTierResult:
    """Every sample question on every tier, under one spend cap for the whole comparison; a
    refusal at the cap stops it, and what was done is kept."""
    result = FourTierResult({tier: TierResult() for tier in config.models.tiers})
    run_id = f"run:{ids.h(['four_tier', [s.key for s in picked]])}"
    spent = 0.0
    causes = {c.id: c.cause for c in ref.causes}
    # group by group, every tier in turn: a stop at the cap cuts all tiers at the same point
    for group in _groups(picked):
        first = group[0]
        by_section = {x.id: x for x in first.sections}
        agent = agent_for(first.question, by_section)
        questions = [s.question for s in group]
        for tier_name, tier_result in result.tiers.items():
            tier = Tier(tier_name)
            size = config.caps.run.specialist_batch_size[tier]
            for batch in batches(questions, by_section, size):
                tier_result.questions += len(batch)
                prepared = prepare_batch(
                    gateway,
                    plant=first.plant,
                    ref=ref,
                    config=config,
                    sections=by_section,
                    questions=batch,
                    agent=agent,
                    ai_remaining=0,
                    tier=tier,
                )
                if isinstance(prepared, BatchOutcome):
                    continue  # too large even trimmed: counted, not valid
                start = timer()
                try:
                    outcome = run_batch(
                        gateway,
                        plant=first.plant,
                        ref=ref,
                        config=config,
                        sections=by_section,
                        questions=batch,
                        agent=agent,
                        budget=RunBudget(run_id, spent, cap_usd),
                        previous_step_id=f"step:{ids.h(['four_tier', tier_name])}",
                        ai_remaining=0,
                        existing_question_ids={q.id for q in questions},
                        prepared=prepared,
                    )
                except BudgetRefused as refused:
                    tier_result.questions -= len(batch)
                    result.stopped = f"stopped at the cap (${cap_usd:.2f}): {refused}"
                    return result
                tier_result.latencies_s.append(timer() - start)
                spent += outcome.cap_cost_usd
                tier_result.cost_usd += outcome.cost_usd
                tier_result.answered += len(batch)
                status = {q.id: q for q in outcome.questions}
                for q in batch:
                    answered = status.get(q.id)
                    valid = answered is not None and answered.status in DONE
                    tier_result.valid += valid
                    tier_result.answers.append(
                        {
                            "key": f"{first.case}:{q.id}",
                            "question": q.text,
                            "valid": valid,
                            "answer": (
                                [
                                    _text(f, causes)
                                    for f in outcome.findings
                                    if f.question_id == q.id
                                ]
                                or (answered.not_credible_reason if answered else None)
                            ),
                        }
                    )
                tier_result.raw.append(
                    {
                        "case": first.case,
                        "agent": agent.value,
                        "question_ids": [q.id for q in batch],
                        "request": {"messages": prepared.conversation, "tools": prepared.tools},
                        "model_calls": [c.model_dump(mode="json") for c in outcome.model_calls],
                    }
                )
    return result


def _dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )


def write_outputs(result: FourTierResult, root: Path) -> None:
    """The summary, each tier's answers (for the hand score), the raw calls (R9), and the score
    sheet (R35): one row per question and tier, filled rows kept."""
    _dump(
        root / "four_tier" / "summary.json",
        {
            "stopped": result.stopped,
            "tiers": {
                tier: {
                    "questions": r.questions,
                    "valid": r.valid,
                    "valid_rate": round(r.valid_rate, 4),
                    "median_latency_s": round(r.median_latency_s, 3),
                    "cost_usd": round(r.cost_usd, 6),
                }
                for tier, r in result.tiers.items()
            },
        },
    )
    for tier, r in result.tiers.items():
        _dump(root / "four_tier" / "answers" / f"{tier}.json", r.answers)
        for n, call in enumerate(r.raw, start=1):
            _dump(
                root / "raw" / "four_tier" / tier / f"{n:03d}-{call['case']}-{call['agent']}.json",
                call,
            )
    sheet = root / SCORES
    kept: dict[tuple[str, str], dict[str, str]] = {}
    if sheet.exists():
        with sheet.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                kept[(row["question_key"], row["tier"])] = row
    rows = []
    for tier, r in result.tiers.items():
        for answer in r.answers:
            old = kept.get((answer["key"], tier))
            rows.append(
                old
                if old is not None and old.get("score")
                else {"question_key": answer["key"], "tier": tier, "score": "", "reason": ""}
            )
    with sheet.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SCORE_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
