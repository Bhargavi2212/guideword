"""The P3-4 piping-leak size rule and the P3-5 task-frequency flag (spec 3.2; plan PR 3, G12).

C20 on a line with `size_mm` above `ranking.pipe_leak_large_above_mm` uses the large-leak
event; at or below it, the small one; a missing size uses the small one, flagged. C14-C17
keep the monthly human-error event, flagged "task frequency assumed — engineer to confirm".
"""

import json
from pathlib import Path
from typing import Any

import pytest

from guideword.config import CapsConfig, Config, load_config
from guideword.ranking.likelihood import (
    PIPE_LEAK_LARGE_EVENT,
    PIPE_LEAK_SMALL_EVENT,
    TASK_FREQUENCY_FLAG,
    likelihood,
)
from guideword.ranking.rank import rank_findings
from guideword.reference import ReferenceSet, load_reference_set
from guideword.runs.case import folded_lines
from guideword.schema import ids
from guideword.schema.enums import (
    Adequacy,
    Confidence,
    FailingComponentType,
    LikelihoodClass,
    SeverityClass,
    Tier,
)
from guideword.schema.plant import Plant
from guideword.schema.records import Finding

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
RUN = "run:test"


@pytest.fixture(scope="module")
def ref() -> ReferenceSet:
    return load_reference_set()


@pytest.fixture(scope="module")
def config() -> Config:
    return load_config(global_budget_usd=25.0)


def _plant(l_12: dict[str, Any] | None = None, l_stm: dict[str, Any] | None = None) -> Plant:
    data: dict[str, Any] = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["lines"][0].update(l_12 or {})
    data["lines"][1].update(l_stm or {})
    for line in data["lines"]:
        if line.get("size_mm") is None:
            line.pop("size_mm", None)
    return Plant.model_validate(data)


def _finding(
    cause: str,
    components: tuple[str, ...],
    kind: FailingComponentType,
    question: str = "nf:L-12",
) -> Finding:
    return Finding(
        id=ids.finding_id(question, Tier.LIGHTNING.value, list(components), cause_id=cause),
        run_id=RUN,
        question_id=question,
        tier=Tier.LIGHTNING,
        cause_id=cause,
        failing_component_type=kind,
        failing_component_ids=list(components),
        consequence="something bad",
        adequacy=Adequacy.UNKNOWN,
        severity_class=SeverityClass.S4,
        severity_reason="test",
        confidence=Confidence.SURE,
    )


def _leak(*lines: str) -> Finding:
    return _finding("C20", lines or ("L-12",), FailingComponentType.PIPE)


def _event(ref: ReferenceSet, event_id: str) -> float:
    return next(e.frequency for e in ref.initiating_events if e.id == event_id)


def _threshold(config: Config) -> float:
    return config.caps.ranking.pipe_leak_large_above_mm


def test_the_threshold_is_150_mm_in_caps(config: Config) -> None:
    assert _threshold(config) == 150


def test_both_leak_events_are_reference_rows(ref: ReferenceSet) -> None:
    rows = {e.id: e for e in ref.initiating_events}
    assert rows[PIPE_LEAK_SMALL_EVENT].unit == rows[PIPE_LEAK_LARGE_EVENT].unit == "per_metre_year"
    c20 = next(c for c in ref.causes if c.id == "C20")
    assert c20.initiating_event_id == PIPE_LEAK_SMALL_EVENT


def test_c20_above_150_mm_uses_the_large_leak_event(ref: ReferenceSet, config: Config) -> None:
    """200 mm, 100 m: IE-PIPE-LEAK-L 1e-06 per metre-year x 100 m = 1e-04 per year (L1),
    in the likelihood and in the screening rank that reads it."""
    plant = _plant({"size_mm": 200, "length_m": 100})
    found = likelihood(_leak(), plant, ref, config.caps)
    assert found.initiating_event_id == PIPE_LEAK_LARGE_EVENT
    assert found.frequency_per_year == pytest.approx(
        _event(ref, PIPE_LEAK_LARGE_EVENT) * 100, rel=1e-9
    )
    assert found.likelihood_class == LikelihoodClass.L1
    assert found.flags == ()
    [ranked] = rank_findings([_leak()], plant, ref, config.caps)
    assert ranked.likelihood == found


def test_c20_at_exactly_150_mm_uses_the_small_leak_event(ref: ReferenceSet, config: Config) -> None:
    found = likelihood(_leak(), _plant({"size_mm": 150, "length_m": 100}), ref, config.caps)
    assert found.initiating_event_id == PIPE_LEAK_SMALL_EVENT
    assert found.frequency_per_year == pytest.approx(
        _event(ref, PIPE_LEAK_SMALL_EVENT) * 100, rel=1e-9
    )
    assert found.flags == ()


def test_c20_without_size_uses_small_and_flags_the_assumption(
    ref: ReferenceSet, config: Config
) -> None:
    found = likelihood(_leak(), _plant({"size_mm": None, "length_m": 100}), ref, config.caps)
    assert found.initiating_event_id == PIPE_LEAK_SMALL_EVENT
    assert found.frequency_per_year == pytest.approx(
        _event(ref, PIPE_LEAK_SMALL_EVENT) * 100, rel=1e-9
    )
    assert found.flags == ("size assumed ≤ 150 mm (L-12.size_mm)",)


def test_c20_without_size_or_length_is_unrated_and_still_flags_the_size(
    ref: ReferenceSet, config: Config
) -> None:
    found = likelihood(_leak(), _plant({"size_mm": None}), ref, config.caps)
    assert found.likelihood_class is None
    assert found.missing_fact_ids == ("L-12.length_m",)
    assert found.flags == ("size assumed ≤ 150 mm (L-12.size_mm)",)


def test_the_threshold_comes_from_caps_not_a_literal(ref: ReferenceSet, config: Config) -> None:
    caps = config.caps.model_copy(
        update={"ranking": config.caps.ranking.model_copy(update={"pipe_leak_large_above_mm": 40})}
    )
    assert isinstance(caps, CapsConfig)
    found = likelihood(_leak(), _plant({"size_mm": 50, "length_m": 100}), ref, caps)
    assert found.initiating_event_id == PIPE_LEAK_LARGE_EVENT
    missing = likelihood(_leak(), _plant({"size_mm": None, "length_m": 100}), ref, caps)
    assert missing.flags == ("size assumed ≤ 40 mm (L-12.size_mm)",)


def test_several_failing_lines_each_use_their_own_event(ref: ReferenceSet, config: Config) -> None:
    """L-12 200 mm x 100 m on the large event plus L-STM 25 mm x 10 m on the small one."""
    plant = _plant({"size_mm": 200, "length_m": 100}, {"size_mm": 25, "length_m": 10})
    found = likelihood(_leak("L-12", "L-STM"), plant, ref, config.caps)
    expected = _event(ref, PIPE_LEAK_LARGE_EVENT) * 100 + _event(ref, PIPE_LEAK_SMALL_EVENT) * 10
    assert found.frequency_per_year == pytest.approx(expected, rel=1e-9)
    # mixed sizes: the cause's own (small) event is named, and the split is flagged
    assert found.initiating_event_id == PIPE_LEAK_SMALL_EVENT
    assert found.flags == (
        f"lines use different leak events: L-12 {PIPE_LEAK_LARGE_EVENT}, "
        f"L-STM {PIPE_LEAK_SMALL_EVENT}",
    )


def test_several_large_lines_name_the_large_event(ref: ReferenceSet, config: Config) -> None:
    plant = _plant({"size_mm": 200, "length_m": 100}, {"size_mm": 300, "length_m": 10})
    found = likelihood(_leak("L-12", "L-STM"), plant, ref, config.caps)
    assert found.initiating_event_id == PIPE_LEAK_LARGE_EVENT
    assert found.frequency_per_year == pytest.approx(
        _event(ref, PIPE_LEAK_LARGE_EVENT) * 110, rel=1e-9
    )
    assert found.flags == ()


@pytest.mark.parametrize("cause", ["C14", "C15", "C16", "C17"])
def test_c14_to_c17_flag_task_frequency_assumed(
    ref: ReferenceSet, config: Config, cause: str
) -> None:
    error = _finding(cause, ("MX-1",), FailingComponentType.OPERATOR, "m:S-MX-1:more:pressure")
    found = likelihood(error, _plant(), ref, config.caps)
    assert found.initiating_event_id == "IE-HE-MONTHLY"
    assert found.frequency_per_year == _event(ref, "IE-HE-MONTHLY")
    assert found.flags == (TASK_FREQUENCY_FLAG,)
    assert TASK_FREQUENCY_FLAG == "task frequency assumed — engineer to confirm"


def test_other_causes_carry_no_flag(ref: ReferenceSet, config: Config) -> None:
    loop = _finding("C01", ("TIC-1",), FailingComponentType.CONTROL_LOOP, "m:S-MX-1:more:pressure")
    assert likelihood(loop, _plant(), ref, config.caps).flags == ()


def test_ranked_lines_carry_the_likelihood_flags(ref: ReferenceSet, config: Config) -> None:
    """G12: the screening report shows the P3-4/5 flags, not only the LOPA records."""
    leak = _leak()
    error = _finding("C15", ("MX-1",), FailingComponentType.OPERATOR, "m:S-MX-1:more:pressure")
    lines = folded_lines(
        [leak, error], _plant({"size_mm": None, "length_m": 100}), ref, config.caps
    )
    by_id = {line["finding_id"]: line for line in lines}
    assert by_id[leak.id]["likelihood_flags"] == ["size assumed ≤ 150 mm (L-12.size_mm)"]
    assert by_id[error.id]["likelihood_flags"] == [TASK_FREQUENCY_FLAG]
