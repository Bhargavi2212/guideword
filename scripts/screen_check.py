"""One whole-plant pass (plant_screen) on a plant, reported as counts only. Bhargavi runs it.

  python scripts/screen_check.py cases/dev/case_h.json --use development --cap 0.05

Uploads the plant, confirms the rule cut, starts a run and advances only its first step, the
plant_screen call (R50); the analysis is never started. Prints whether the answer was valid,
how many hypotheses came back, were kept and were dropped (by kind of reason), how many
component and chemical IDs were not in the plant, and the question-link counts. It never
prints a hypothesis's words, its rank, or an ID, so the output can be shared. The run store
defaults to `screen_check.db`, apart from the `run_case.py` store, so a later full run of the
same plant does not pick up this one.
"""

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from guideword.config import Config, load_config
from guideword.gateway.cache import ResponseCache
from guideword.gateway.client import Gateway, GatewayResult
from guideword.gateway.ledgers import Ledger, ledger_for
from guideword.gateway.transport import OpenAITransport, Transport
from guideword.logs import configure
from guideword.reference import load_reference_set
from guideword.runs.case import InvalidPlant, prepare_plant, start_case
from guideword.runs.db import make_session_factory
from guideword.runs.machine import advance
from guideword.runs.plants import PlantRepository
from guideword.runs.store import RunRepository
from guideword.schema import ids
from guideword.schema.enums import BudgetUse, EventType
from guideword.schema.plant import Plant
from guideword.screen.schema import _all_ids, parse_answer
from guideword.screen.step import JOB, PlantScreenStepper
from guideword.settings import Settings

PHASE = "2"
USES = (BudgetUse.DEVELOPMENT.value, BudgetUse.TEST_5.value)
DEFAULT_DB = Path(__file__).resolve().parents[1] / "screen_check.db"
# the kinds of drop reason, by the words code's checks use (screen/schema.py, screen/step.py)
REASONS = (
    ("not in this plant", "unknown component"),
    ("not a chemical of this plant", "unknown chemical"),
    ("cannot fail as a", "component cannot fail as that type"),
    ("is not a library cause", "unknown library cause"),
    ("fails a", "library cause of another component type"),
    ("needs cause_text", "outside-library cause without text"),
    ("the answer was invalid", "answer invalid as a whole"),
    ("no usable answer", "answer unusable"),
)


class _Keeping(Gateway):
    """The gateway, keeping the final answer text of each call it makes, as the step read it."""

    answers: list[str | None]

    def call(self, **kwargs: Any) -> GatewayResult:
        result = super().call(**kwargs)
        self.answers = [*getattr(self, "answers", []), result.content]
        return result


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("plant", type=Path, help="the plant file")
    parser.add_argument("--use", choices=USES, default=BudgetUse.DEVELOPMENT.value)
    parser.add_argument("--cap", type=float, required=True, help="run spend cap in USD")
    return parser.parse_args(argv)


def _kind(reason: str) -> str:
    return next((label for words, label in REASONS if words in reason), "other")


def summary(
    runs: RunRepository, run_id: str, plant: Plant, answer_text: str | None
) -> dict[str, Any]:
    """Counts only: nothing here carries a hypothesis's words, rank or IDs."""
    calls = [c for c in runs.model_calls(run_id) if c.job == JOB]
    events = runs.events(run_id)
    dropped = [e.payload for e in events if e.type == EventType.HYPOTHESIS_DROPPED]
    kept = runs.hypotheses(run_id)
    answer = parse_answer(answer_text)
    returned = answer.hypotheses if answer is not None else []
    plant_ids = _all_ids(plant)
    chemicals = {c.id for c in plant.chemicals}
    by_kind: dict[str, int] = {}
    for payload in dropped:
        kind = _kind(str(payload.get("reason", "")))
        by_kind[kind] = by_kind.get(kind, 0) + 1
    return {
        "calls": [
            {
                "outcome": c.outcome,
                "finish_reason": c.finish_reason,
                "attempts": c.attempts,
                "cache_hit": c.cache_hit,
                "cost_usd": c.cost_usd,
            }
            for c in calls
        ],
        "cap_hits": [str(e.payload.get("reason")) for e in events if e.type == EventType.CAP_HIT],
        "returned": len(returned),
        "kept": len(kept),
        "dropped": sum(1 for p in dropped if p.get("rank") is not None),
        "dropped_by_kind": dict(sorted(by_kind.items())),
        "unknown_component_ids": sum(
            1 for h in returned for c in h.component_ids if c not in plant_ids
        ),
        "unknown_chemical_ids": sum(
            1 for h in returned for c in h.chemical_ids if c not in chemicals
        ),
        "linked_questions": len({q for h in kept for q in h.question_ids}),
        "kept_without_links": sum(1 for h in kept if not h.question_ids),
        "spent_usd": runs.get(run_id).spent_usd,  # type: ignore[union-attr]
    }


def _print(result: dict[str, Any]) -> None:
    for call in result["calls"]:
        print(
            f"plant_screen call: outcome {call['outcome']}, finish {call['finish_reason']}, "
            f"attempts {call['attempts']}, cache hit {call['cache_hit']}, "
            f"${call['cost_usd']:.4f}"
        )
    if not result["calls"]:
        print("plant_screen call: none recorded")
    for reason in result["cap_hits"]:
        print(f"cap hit: {reason}")
    print(
        f"hypotheses: returned {result['returned']}, kept {result['kept']}, "
        f"dropped {result['dropped']}"
    )
    for kind, count in result["dropped_by_kind"].items():
        print(f"  dropped, {kind}: {count}")
    print(
        f"unknown component IDs {result['unknown_component_ids']}, "
        f"unknown chemical IDs {result['unknown_chemical_ids']}"
    )
    print(
        f"questions linked {result['linked_questions']}; "
        f"kept hypotheses linking none {result['kept_without_links']}"
    )
    print(f"spent ${result['spent_usd']:.4f}")


def main(
    argv: Sequence[str] | None = None,
    *,
    transport: Transport | None = None,
    config: Config | None = None,
    settings: Settings | None = None,
    ledger: Ledger | None = None,
    clock: Callable[[], datetime] | None = None,
) -> int:
    args = _arguments(argv)
    configure()
    if settings is None:
        settings = Settings(database_url=f"sqlite:///{DEFAULT_DB.as_posix()}")
    config = (
        config if config is not None else load_config(global_budget_usd=settings.global_budget_usd)
    )
    clock = clock if clock is not None else (lambda: datetime.now(UTC))
    ref = load_reference_set()
    sessions = make_session_factory(settings.database_url)
    plants = PlantRepository(sessions)
    runs = RunRepository(sessions, clock)
    raw = json.loads(args.plant.read_text(encoding="utf-8"))
    try:
        record = prepare_plant(plants, raw, ref)
    except InvalidPlant as invalid:
        print(f"the plant file does not validate: {invalid}", file=sys.stderr)
        return 1
    try:
        run = start_case(plants, runs, ref, config, record.id, args.cap)
    except ids.CapReachedError as refused:
        print(f"refused: {refused}", file=sys.stderr)
        return 1
    if run.step != JOB:
        print(f"this run is past its plant_screen step ({run.step}); use a new store")
        return 1
    gateway = _Keeping(
        config=config,
        transport=transport if transport is not None else OpenAITransport(settings),
        cache=ResponseCache(sessions),
        ledger=ledger if ledger is not None else ledger_for(settings, sessions),
        use=BudgetUse(args.use),
        phase=PHASE,
        clock=clock,
    )
    screen = PlantScreenStepper(gateway, config=config, ref=ref, plant=record.plant_file)
    advance(runs, run.id, {JOB: screen})
    answers = getattr(gateway, "answers", [])
    _print(summary(runs, run.id, record.plant_file, answers[-1] if answers else None))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
