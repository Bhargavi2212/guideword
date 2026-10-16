"""The tiered list (spec 2b.4; R50; plan G1, G2, G4, Q1): confirmed hypotheses, then the
other scenarios the pipeline found, then hypotheses no check supported. Code builds every tier;
only the confirmed and unconfirmed tiers follow the hypothesis rank."""

import json
from pathlib import Path

import pytest

from guideword.config import Config, load_config
from guideword.questions.build import build_questions
from guideword.ranking.rank import fold, rank_findings
from guideword.ranking.tiers import tiered
from guideword.reference import ReferenceSet, load_reference_set
from guideword.schema import ids
from guideword.schema.enums import SeverityClass, ShortlistTier
from guideword.schema.plant import Plant
from guideword.schema.records import Finding, Hypothesis, Question
from guideword.screen.link import question_links
from guideword.sections.rules import rule_cut

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
RUN = "run:0123456789abcdef"


@pytest.fixture(scope="module")
def ref() -> ReferenceSet:
    return load_reference_set()


@pytest.fixture(scope="module")
def config() -> Config:
    return load_config(global_budget_usd=25.0)


@pytest.fixture(scope="module")
def plant_and_questions(ref: ReferenceSet) -> tuple[Plant, list[Question], list]:
    plant = Plant.model_validate(json.loads(EXAMPLE.read_text(encoding="utf-8")))
    sections = rule_cut(plant, "plant:x:0")
    return plant, build_questions(plant, sections, ref, RUN), sections


def finding(
    question: str, components: list[str], kind: str, cause: str, severity: SeverityClass
) -> Finding:
    return Finding(
        id=ids.finding_id(question, "lightning", components, cause_id=cause),
        run_id=RUN,
        question_id=question,
        tier="lightning",
        cause_id=cause,
        failing_component_type=kind,
        failing_component_ids=components,
        consequence=f"consequence of {cause} on {components[0]}",
        adequacy="unknown",
        severity_class=severity,
        severity_reason="test",
        confidence="sure",
    )


def hyp(
    rank: int,
    components: list[str],
    kind: str,
    cause: str,
    plant_q: tuple,
    chemicals: list[str] | None = None,
) -> Hypothesis:
    plant, questions, sections = plant_q
    return Hypothesis(
        id=ids.hypothesis_id(rank, f"mechanism {rank}", components),
        run_id=RUN,
        rank=rank,
        mechanism=f"mechanism {rank}",
        component_ids=components,
        chemical_ids=chemicals or [],
        failing_component_type=kind,
        cause_id=cause,
        consequence=f"hypothesis consequence {rank}",
        reason="test",
        question_ids=question_links(components, chemicals or [], kind, plant, sections, questions),
    )


@pytest.fixture
def case(plant_and_questions: tuple, ref: ReferenceSet, config: Config) -> dict:
    plant, questions, _ = plant_and_questions
    pair_a = finding("pair:KOH:SIH", ["P-CHARGE-1"], "operator", "C14", SeverityClass.S3)
    pair_b = finding("pair:KOH:SIH", ["P-CHARGE-2"], "operator", "C14", SeverityClass.S4)
    fire = finding("m:S-MX-1:more:pressure", ["BLDG-1"], "external", "C22", SeverityClass.S5)
    loop = finding("m:S-MX-1:more:temperature", ["TIC-1"], "control_loop", "C01", SeverityClass.S2)
    findings = [pair_a, pair_b, fire, loop]
    h1 = hyp(1, ["P-CHARGE-1"], "operator", "C14", plant_and_questions, ["KOH", "SIH"])
    h2 = hyp(2, ["P-CHARGE-2"], "operator", "C14", plant_and_questions, ["KOH", "SIH"])
    h3 = hyp(3, ["TOTE-1"], "tank", "C21", plant_and_questions)
    ranked = rank_findings(findings, plant, ref, config.caps)
    return {
        "findings": findings,
        "hyps": [h1, h2, h3],
        "ranked": ranked,
        "questions": questions,
        "plant": plant,
    }


def test_tier_order_confirmed_also_found_unconfirmed(case: dict) -> None:
    lines = tiered(case["ranked"], case["hyps"], case["findings"], case["questions"])
    tiers = [line.tier for line in lines]
    assert tiers == sorted(
        tiers,
        key=[ShortlistTier.CONFIRMED, ShortlistTier.ALSO_FOUND, ShortlistTier.UNCONFIRMED].index,
    )
    assert [line.hypothesis.rank for line in lines if line.tier == ShortlistTier.CONFIRMED] == [
        1,
        2,
    ]  # type: ignore[union-attr]
    [unconfirmed] = [line for line in lines if line.tier == ShortlistTier.UNCONFIRMED]
    assert (
        unconfirmed.hypothesis is not None
        and unconfirmed.hypothesis.rank == 3
        and unconfirmed.lead is None
    )


def test_lead_scenario_is_first_in_code_order_and_the_rest_fold_under_it(case: dict) -> None:
    """G1: both pair findings support both hypotheses (same pair, same cause); the first line's
    lead is the one first in the spec 2.6 order (the S4), the other folds under it."""
    lines = tiered(case["ranked"], case["hyps"], case["findings"], case["questions"])
    first = lines[0]
    order = [r.finding.id for r in case["ranked"]]
    support = sorted(first.support_ids, key=order.index)
    assert first.lead is not None and first.lead.finding.id == support[0]
    assert [r.finding.id for r in first.folded] == support[1:]


def test_a_scenario_supporting_two_hypotheses_shows_once_under_the_higher(case: dict) -> None:
    """G2: H2 is supported by the same findings, all shown under H1, so H2 stays a confirmed
    line with nothing folded under it and names where its support is shown."""
    lines = tiered(case["ranked"], case["hyps"], case["findings"], case["questions"])
    second = lines[1]
    assert second.hypothesis is not None and second.hypothesis.rank == 2
    assert second.folded == ()
    assert set(second.shown_under) == set(second.support_ids)
    shown = [
        r.finding.id
        for line in lines
        for r in ([line.lead] if line.lead and not line.shown_elsewhere else []) + list(line.folded)
    ]
    assert len(shown) == len(set(shown))


def test_also_found_never_repeats_a_confirmed_lines_scenarios(case: dict) -> None:
    lines = tiered(case["ranked"], case["hyps"], case["findings"], case["questions"])
    confirmed = {
        i for line in lines if line.tier == ShortlistTier.CONFIRMED for i in line.support_ids
    }
    also = [line for line in lines if line.tier == ShortlistTier.ALSO_FOUND]
    also_ids = {r.finding.id for line in also for r in [line.lead, *line.folded] if r is not None}
    assert also_ids and not also_ids & confirmed
    assert also_ids | confirmed == {f.id for f in case["findings"]}


def test_codeorder_keeps_membership_and_orders_by_code(case: dict) -> None:
    """G4: the same lines; confirmed by their lead's place in the code order, unconfirmed by ID."""
    model = tiered(case["ranked"], case["hyps"], case["findings"], case["questions"])
    code = tiered(
        case["ranked"], case["hyps"], case["findings"], case["questions"], code_order=True
    )

    def members(lines: list) -> set:
        return {
            (
                line.tier,
                line.hypothesis.id if line.hypothesis else None,
                line.lead.finding.id if line.lead else None,
            )
            for line in lines
        }

    assert members(model) == members(code)
    order = [r.finding.id for r in case["ranked"]]
    confirmed = [line for line in code if line.tier == ShortlistTier.CONFIRMED]
    keys = [(order.index(line.lead.finding.id), line.hypothesis.id) for line in confirmed]  # type: ignore[union-attr]
    assert keys == sorted(keys)


def test_with_no_hypotheses_the_tiers_are_the_folded_list(case: dict) -> None:
    lines = tiered(case["ranked"], [], case["findings"], case["questions"])
    assert {line.tier for line in lines} == {ShortlistTier.ALSO_FOUND}
    folded = fold(case["ranked"])
    assert [(line.lead.finding.id if line.lead else None) for line in lines] == [
        f.worst.finding.id for f in folded
    ]


def test_tiers_are_a_pure_function_of_their_inputs(case: dict) -> None:
    a = tiered(case["ranked"], case["hyps"], case["findings"], case["questions"])
    b = tiered(
        case["ranked"],
        list(reversed(case["hyps"])),
        list(reversed(case["findings"])),
        case["questions"],
    )
    assert a == b
