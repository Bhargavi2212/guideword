"""Likelihood and the risk-matrix ranking, all code (spec 2.6; plan R11, R12, R28)."""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from guideword.config import Config, load_config
from guideword.ranking.likelihood import band_for, likelihood
from guideword.ranking.rank import rank_findings
from guideword.reference import ReferenceSet, load_reference_set
from guideword.schema import ids
from guideword.schema.enums import (
    Adequacy,
    Confidence,
    FailingComponentType,
    LikelihoodClass,
    RiskRating,
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


def _plant(**line_12: Any) -> Plant:
    data: dict[str, Any] = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["lines"][0].update(line_12)
    data["planned_work"].append({"id": "W-LIFT", "type": "lifting", "location_id": "BLDG-1"})
    return Plant.model_validate(data)


def _finding(
    question: str = "m:S-MX-1:more:pressure",
    cause: str = "C01",
    kind: FailingComponentType = FailingComponentType.CONTROL_LOOP,
    components: tuple[str, ...] = ("TIC-1",),
    severity: SeverityClass | None = SeverityClass.S4,
    tier: Tier = Tier.LIGHTNING,
    confidence: Confidence = Confidence.SURE,
    cause_text: str | None = None,
) -> Finding:
    outside = cause == "outside_library"
    return Finding(
        id=ids.finding_id(
            question,
            tier.value,
            list(components),
            cause_id=None if outside else cause,
            cause_text=cause_text if outside else None,
        ),
        run_id=RUN,
        question_id=question,
        tier=tier,
        cause_id=cause,
        cause_text=cause_text,
        failing_component_type=kind,
        failing_component_ids=list(components),
        consequence="something bad",
        adequacy=Adequacy.UNKNOWN,
        severity_class=severity,
        severity_reason="test" if severity else None,
        confidence=confidence,
    )


# --- likelihood ------------------------------------------------------------------------------


def test_c01_ie_bpcs_0_1_is_l4_and_s4_rating_from_the_matrix(
    ref: ReferenceSet, config: Config
) -> None:
    """Hand-worked: C01 → IE-BPCS, 0.1 per year → L4 (bands include their upper edge);
    S4 × L4 in risk_matrix.csv is high."""
    found = likelihood(_finding(), _plant(), ref, config.caps)
    assert (found.initiating_event_id, found.frequency_per_year, found.likelihood_class) == (
        "IE-BPCS",
        0.1,
        LikelihoodClass.L4,
    )
    [ranked] = rank_findings([_finding()], _plant(), ref, config.caps)
    matrix = {(r.severity_class, r.likelihood_class): r.rating for r in ref.risk_matrix}
    assert ranked.rating == matrix[(SeverityClass.S4, LikelihoodClass.L4)] == RiskRating.HIGH


@pytest.mark.parametrize(
    ("frequency", "band"),
    [
        (0.1, "L4"),
        (0.10001, "L5"),
        (0.01, "L3"),
        (0.001, "L2"),
        (0.0001, "L1"),
        (0.00001, "L1"),
        (5.0, "L5"),
    ],
)
def test_band_edges_are_upper_inclusive(ref: ReferenceSet, frequency: float, band: str) -> None:
    assert band_for(frequency, ref) == LikelihoodClass(band)


def test_c20_without_length_is_unrated_naming_line_length_m(
    ref: ReferenceSet, config: Config
) -> None:
    leak = _finding("nf:L-12", "C20", FailingComponentType.PIPE, ("L-12",))
    found = likelihood(leak, _plant(), ref, config.caps)
    assert found.likelihood_class is None
    assert found.missing_fact_ids == ("L-12.length_m",)
    [ranked] = rank_findings([leak], _plant(), ref, config.caps)
    assert ranked.rating is None and ranked.missing_fact_ids == ("L-12.length_m",)


def test_c20_with_length_converts_per_metre_year(ref: ReferenceSet, config: Config) -> None:
    leak = _finding("nf:L-12", "C20", FailingComponentType.PIPE, ("L-12",))
    found = likelihood(leak, _plant(length_m=100), ref, config.caps)
    assert found.frequency_per_year == pytest.approx(1e-3)
    assert found.likelihood_class == LikelihoodClass.L2


def test_c24_without_lifts_is_unrated(ref: ReferenceSet, config: Config) -> None:
    crane = _finding("work:W-LIFT:MX-1", "C24", FailingComponentType.EXTERNAL, ("BLDG-1",))
    found = likelihood(crane, _plant(), ref, config.caps)
    assert found.likelihood_class is None
    assert found.missing_fact_ids == ("W-LIFT.lifts_per_year",)


def test_outside_library_gets_highest_frequency_of_its_type_flagged(
    ref: ReferenceSet, config: Config
) -> None:
    """Control-loop causes C01-C03 all start from IE-BPCS (0.1 per year)."""
    odd = _finding(cause="outside_library", cause_text="controller firmware bug")
    found = likelihood(odd, _plant(), ref, config.caps)
    assert (found.frequency_per_year, found.assumed) == (0.1, True)
    assert found.likelihood_class == LikelihoodClass.L4


def test_outside_library_type_with_no_library_cause_gets_the_default_flagged(
    ref: ReferenceSet, config: Config
) -> None:
    no_loops = replace(
        ref, causes=tuple(c for c in ref.causes if c.failing_component_type != "control_loop")
    )
    odd = _finding(cause="outside_library", cause_text="controller firmware bug")
    found = likelihood(odd, _plant(), no_loops, config.caps)
    default = config.caps.ranking.outside_library_default_frequency_per_year
    assert (found.frequency_per_year, found.assumed) == (default, True)


def test_per_opportunity_is_unrated(ref: ReferenceSet, config: Config) -> None:
    by_event = {e.unit: e.id for e in ref.initiating_events}
    cause = next(c for c in ref.causes if c.id == "C14")
    opp_ref = replace(
        ref,
        causes=tuple(
            c.model_copy(update={"initiating_event_id": by_event["per_opportunity"]})
            if c.id == "C14"
            else c
            for c in ref.causes
        ),
    )
    assert cause.initiating_event_id != by_event["per_opportunity"]
    found = likelihood(
        _finding("proc:P-CHARGE-1:wrong", "C14", FailingComponentType.OPERATOR, ("P-CHARGE-1",)),
        _plant(),
        opp_ref,
        config.caps,
    )
    assert found.likelihood_class is None
    assert found.note is not None and "per_opportunity" in found.note


# --- the order -------------------------------------------------------------------------------


def test_ties_broken_by_severity_then_frequency_then_id(ref: ReferenceSet, config: Config) -> None:
    plant = _plant(length_m=1000)
    high_s4 = _finding("m:S-MX-1:more:pressure")  # L4, S4: high
    high_s3 = _finding("m:S-MX-1:more:temperature", severity=SeverityClass.S3)  # L4 x S3: medium
    leak = _finding(
        "nf:L-12", "C20", FailingComponentType.PIPE, ("L-12",), severity=SeverityClass.S5
    )  # 1e-2 → L3; S5+L3 = 8 high
    unrated = _finding(
        "nf:L-12", "C20", FailingComponentType.PIPE, ("L-12",), severity=None, tier=Tier.SUPER
    )
    order = rank_findings([unrated, high_s3, high_s4, leak], plant, ref, config.caps)
    assert [r.finding.id for r in order] == [leak.id, high_s4.id, high_s3.id, unrated.id]
    assert [r.rank for r in order] == [1, 2, 3, 4]
    assert order[-1].rating is None and order[-1].unrated_reason == "no severity"


def test_same_rating_and_severity_higher_frequency_first_then_id(
    ref: ReferenceSet, config: Config
) -> None:
    plant = _plant(length_m=10000)  # C20 → 0.1: L4, the same band as C01
    a = _finding("m:S-MX-1:more:pressure")
    b = _finding("nf:L-12", "C20", FailingComponentType.PIPE, ("L-12",))
    order = rank_findings([b, a], plant, ref, config.caps)
    # both 0.1 per year, S4 → the same rating and frequency: finding ID decides
    assert [r.finding.id for r in order] == sorted([a.id, b.id])


def test_ultra_reanswer_supersedes_the_unsure_finding(ref: ReferenceSet, config: Config) -> None:
    """R28: every finding is ranked; the earlier unsure one names its re-answer."""
    unsure = _finding(confidence=Confidence.UNSURE)
    ultra = _finding(tier=Tier.ULTRA)
    order = rank_findings([unsure, ultra], _plant(), ref, config.caps)
    by_id = {r.finding.id: r for r in order}
    assert by_id[unsure.id].superseded_by == ultra.id
    assert by_id[ultra.id].superseded_by is None
    assert len(order) == 2


def test_ranking_is_a_pure_function_of_its_inputs(ref: ReferenceSet, config: Config) -> None:
    findings = [_finding(), _finding("m:S-MX-1:more:temperature", severity=SeverityClass.S2)]
    assert rank_findings(findings, _plant(), ref, config.caps) == rank_findings(
        list(reversed(findings)), _plant(), ref, config.caps
    )


# --- R48: the display fold ------------------------------------------------------------------------


def test_fold_shows_one_line_per_cause_and_components_worst_first(
    ref: ReferenceSet, config: Config
) -> None:
    """The same cause on the same components found from several questions is one line, the
    worst-ranked finding shown and the rest folded underneath; other causes stay apart."""
    from guideword.ranking.rank import fold  # noqa: PLC0415

    plant = _plant()
    worse = _finding("m:S-MX-1:more:pressure", severity=SeverityClass.S5)
    same = _finding("m:S-MX-1:more:temperature", severity=SeverityClass.S3)
    other_section = _finding("m:S-TOTE-1:more:pressure", severity=SeverityClass.S2)
    different = _finding("m:S-MX-1:less:flow", cause="C02", severity=SeverityClass.S4)
    ranked = rank_findings([same, different, other_section, worse], plant, ref, config.caps)
    lines = fold(ranked)
    assert [line.rank for line in lines] == [1, 2]
    assert lines[0].worst.finding.id == worse.id
    assert {r.finding.id for r in lines[0].folded} == {same.id, other_section.id}
    assert [r.finding.id for r in lines[0].folded] == [
        r.finding.id for r in ranked if r.finding.id in {same.id, other_section.id}
    ]
    assert lines[1].worst.finding.id == different.id and lines[1].folded == ()
    assert sum(1 + len(line.folded) for line in lines) == len(ranked)


def test_fold_compares_outside_library_text_after_normalising(
    ref: ReferenceSet, config: Config
) -> None:
    from guideword.ranking.rank import fold  # noqa: PLC0415

    outside = {
        "cause": "outside_library",
        "kind": FailingComponentType.EXTERNAL,
        "components": ("ROOF",),
    }
    a = _finding("m:S-MX-1:more:pressure", cause_text="Roof  collapse", **outside)  # type: ignore[arg-type]
    b = _finding("m:S-MX-1:less:pressure", cause_text="roof collapse", **outside)  # type: ignore[arg-type]
    c = _finding("m:S-MX-1:less:flow", cause_text="roof leak", **outside)  # type: ignore[arg-type]
    lines = fold(rank_findings([a, b, c], _plant(), ref, config.caps))
    assert len(lines) == 2
