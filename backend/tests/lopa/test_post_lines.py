"""The post-analysis lines, pure code (Phase 3 plan PR 5): which lines get full, code-only or
no LOPA, the chain checks (Q6, Q7, G7), a chain's tier and initiating frequency, and the
shortlist, where a line with no LOPA stays with its reason (Bhargavi, 2026-10-19)."""

import json
from pathlib import Path

import pytest

from guideword.chains.connector import (
    MORE_THAN_TWO_FLAG,
    chain_flags,
    chain_problem,
)
from guideword.config import Config
from guideword.lopa.engine import CODE_ONLY_FLAG, NoLopa, lopa_record
from guideword.lopa.lines import (
    HIGH_SEVERITY_NO_LOPA,
    chain_tier,
    display_lines,
    lopa_plan,
    shortlist,
)
from guideword.ranking.likelihood import likelihood
from guideword.ranking.rank import rank_findings
from guideword.ranking.tiers import TieredLine
from guideword.reference import ReferenceSet
from guideword.runs.plants import plant_facts
from guideword.schema import ids
from guideword.schema.enums import (
    Adequacy,
    Confidence,
    FailingComponentType,
    QuestionOrigin,
    QuestionStatus,
    SeverityClass,
    ShortlistTier,
    Tier,
)
from guideword.schema.plant import Plant
from guideword.schema.records import (
    OUTSIDE_LIBRARY,
    Chain,
    Finding,
    Hypothesis,
    LopaRecord,
    Question,
)

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
RUN = "run:post-lines"


@pytest.fixture(scope="module")
def plant() -> Plant:
    return Plant.model_validate(json.loads(EXAMPLE.read_text(encoding="utf-8")))


def question(qid: str) -> Question:
    kind = ids.parse_question_id(qid).kind
    return Question(
        id=qid,
        run_id=RUN,
        kind=kind,
        origin=QuestionOrigin.CROSS_LIST,
        status=QuestionStatus.ANSWERED,
        text="q",
    )


def finding(
    qid: str,
    components: list[str],
    *,
    cause_id: str | None = None,
    cause_text: str | None = None,
    kind: FailingComponentType = FailingComponentType.EXTERNAL,
    severity: SeverityClass | None = None,
) -> Finding:
    fid = ids.finding_id(qid, Tier.LIGHTNING, components, cause_id=cause_id, cause_text=cause_text)
    return Finding(
        id=fid,
        run_id=RUN,
        question_id=qid,
        tier=Tier.LIGHTNING,
        cause_id=cause_id or OUTSIDE_LIBRARY,
        cause_text=cause_text,
        failing_component_type=kind,
        failing_component_ids=components,
        consequence="a release",
        adequacy=Adequacy.UNKNOWN,
        confidence=Confidence.SURE,
        severity_class=severity,
        severity_reason="test" if severity else None,
    )


def chain(links: list[str], severity: SeverityClass | None = SeverityClass.S4) -> Chain:
    return Chain(
        id=ids.chain_id(links),
        run_id=RUN,
        links=links,
        description="d",
        reason="r",
        severity_class=severity,
        severity_reason="test" if severity else None,
    )


def records_for(plan: list, plant: Plant, ref: ReferenceSet, config: Config) -> list[LopaRecord]:
    """Code-only records for every planned line (what the step writes without arguments)."""
    out = []
    for p in plan:
        if p.scenario is None:
            continue
        found = lopa_record(
            p.scenario, run_id=RUN, plant=plant, ref=ref, caps=config.caps, arguments=None
        )
        if isinstance(found, LopaRecord):
            out.append(found)
    return out


# --- the chain checks (spec 3.1; Q6, G7) ---------------------------------------------------


def test_chain_validator_rejects_unknown_links_and_facts_only() -> None:
    findings = {"f:a", "f:b"}
    facts = {"MX-1.design_pressure_kpa", "HV-12.normal_position"}
    assert chain_problem(["f:a", "f:b"], findings, facts) is None
    assert chain_problem(["f:a", "MX-1.design_pressure_kpa"], findings, facts) is None
    unknown = chain_problem(["f:a", "f:nope"], findings, facts)
    assert unknown is not None and "f:nope" in unknown
    facts_only = chain_problem(
        ["MX-1.design_pressure_kpa", "HV-12.normal_position"], findings, facts
    )
    assert facts_only is not None and "finding" in facts_only
    assert chain_problem(["f:a"], findings, facts) is not None
    assert chain_problem(["f:a", "f:a"], findings, facts) is not None


def test_a_fact_link_must_match_a_fact_id_exactly() -> None:
    facts = {"MX-1.design_pressure_kpa"}
    assert chain_problem(["f:a", "MX-1.design_pressure_kpa"], {"f:a"}, facts) is None
    for near in (
        "MX-1.design_pressure",
        "mx-1.design_pressure_kpa",
        "MX-1",
        "MX-1.design_pressure_kpa ",
    ):
        assert chain_problem(["f:a", near], {"f:a"}, facts) is not None, near


def test_more_than_two_independent_failures_are_flagged_never_filtered() -> None:
    a = finding("env:SIH:water", ["BLDG-1"], cause_text="a")
    b = finding("env:SIH:air", ["MX-1"], cause_text="b")
    c = finding("env:KOH:water", ["P-1"], cause_text="c")
    d = finding("env:KOH:air", ["MX-1", "P-1"], cause_text="d")
    by_id = {f.id: f for f in (a, b, c, d)}
    assert chain_flags([a.id, b.id, c.id], by_id) == [MORE_THAN_TWO_FLAG]
    # d overlaps b and c: two independent failures, not three
    assert chain_flags([a.id, b.id, c.id, d.id], by_id) == []
    assert chain_flags([a.id, b.id, "MX-1.design_pressure_kpa"], by_id) == []


# --- tiers and frequencies of chains (3.1, 6.3; Q7) ------------------------------------------


def test_chain_takes_the_tier_of_its_highest_member(
    plant: Plant, ref: ReferenceSet, config: Config
) -> None:
    f1 = finding("env:SIH:water", ["BLDG-1"], cause_text="one", severity=SeverityClass.S3)
    f2 = finding("env:SIH:air", ["BLDG-1"], cause_text="two", severity=SeverityClass.S3)
    f3 = finding("env:KOH:water", ["BLDG-1"], cause_text="two", severity=SeverityClass.S3)
    ranked = {r.finding.id: r for r in rank_findings([f1, f2, f3], plant, ref, config.caps)}
    h = Hypothesis(
        id=ids.hypothesis_id(1, "m", ["BLDG-1"]),
        run_id=RUN,
        rank=1,
        mechanism="m",
        component_ids=["BLDG-1"],
        failing_component_type=FailingComponentType.EXTERNAL,
        cause_id=OUTSIDE_LIBRARY,
        cause_text="one",
        consequence="c",
        reason="r",
    )
    lines = [
        TieredLine(ShortlistTier.CONFIRMED, h, ranked[f1.id], ()),
        TieredLine(ShortlistTier.ALSO_FOUND, None, ranked[f2.id], (ranked[f3.id],)),
        TieredLine(ShortlistTier.UNCONFIRMED, h, None, ()),
    ]
    assert chain_tier(chain([f3.id, "MX-1.design_pressure_kpa"]), lines) == (
        ShortlistTier.ALSO_FOUND,
        2,
    )
    assert chain_tier(chain([f3.id, f1.id]), lines) == (ShortlistTier.CONFIRMED, 1)


def _chain_plan(
    links: list[str], findings: list[Finding], plant: Plant, ref: ReferenceSet, config: Config
) -> LopaRecord:
    questions = [question(f.question_id) for f in findings]
    lines = display_lines(findings, [], questions, [], plant, ref, config.caps)
    the_chain = chain(links)
    plan = lopa_plan(lines, [the_chain], findings, questions, [], top_n=10)
    planned = next(p for p in plan if p.target_id == the_chain.id)
    assert planned.kind == "full" and planned.scenario is not None
    record = lopa_record(
        planned.scenario, run_id=RUN, plant=plant, ref=ref, caps=config.caps, arguments=None
    )
    assert isinstance(record, LopaRecord)
    return record


def test_chain_initiating_frequency_is_the_first_finding_links(
    plant: Plant, ref: ReferenceSet, config: Config
) -> None:
    tank = finding(
        "env:SIH:heat",
        ["TOTE-1"],
        cause_id="C21",
        kind=FailingComponentType.TANK,
        severity=SeverityClass.S3,
    )
    outside = finding("env:KOH:air", ["BLDG-1"], cause_text="outside", severity=SeverityClass.S3)
    f_tank = likelihood(tank, plant, ref, config.caps).frequency_per_year
    f_out = likelihood(outside, plant, ref, config.caps).frequency_per_year
    assert f_tank is not None and f_out is not None and f_tank != f_out
    first_tank = _chain_plan([tank.id, outside.id], [tank, outside], plant, ref, config)
    first_out = _chain_plan([outside.id, tank.id], [tank, outside], plant, ref, config)
    assert first_tank.initiating_frequency_per_year == f_tank
    assert first_out.initiating_frequency_per_year == f_out


def test_a_chain_is_never_ranked_down_for_needing_two_failures(
    plant: Plant, ref: ReferenceSet, config: Config
) -> None:
    tank = finding(
        "env:SIH:heat",
        ["TOTE-1"],
        cause_id="C21",
        kind=FailingComponentType.TANK,
        severity=SeverityClass.S3,
    )
    outside = finding("env:KOH:air", ["BLDG-1"], cause_text="outside", severity=SeverityClass.S3)
    record = _chain_plan([outside.id, tank.id], [tank, outside], plant, ref, config)
    first = likelihood(outside, plant, ref, config.caps).frequency_per_year
    tolerable = next(
        t.tolerable_per_year for t in ref.tolerable_frequencies if t.severity_class == "S4"
    )
    credited = [layer.pfd for layer in record.layers if layer.credited and layer.pfd]
    assert credited == []  # code-only here: nothing credited
    # only the first finding link's frequency: no factor for the second failure
    assert record.gap == pytest.approx(first / tolerable, rel=1e-12)  # type: ignore[operator]


# --- which lines get LOPA (3.2; Q10, Q11) and the shortlist ----------------------------------


def test_a_line_with_no_lopa_stays_on_the_shortlist_with_its_reason_and_s4_s5_are_flagged(
    plant: Plant, ref: ReferenceSet, config: Config
) -> None:
    rated = finding("pair:KOH:SIH", ["BLDG-1"], cause_text="rated", severity=SeverityClass.S3)
    no_severity = finding("env:SIH:water", ["BLDG-1"], cause_text="no severity")
    # a per_metre_year cause that names no line: no frequency and no missing fact (NoLopa)
    no_frequency = finding(
        "env:KOH:water",
        ["MX-1"],
        cause_id="C20",
        kind=FailingComponentType.PIPE,
        severity=SeverityClass.S4,
    )
    findings = [rated, no_severity, no_frequency]
    questions = [question(f.question_id) for f in findings]
    lines = display_lines(findings, [], questions, [], plant, ref, config.caps)
    plan = lopa_plan(lines, [], findings, questions, [], top_n=10)
    records = records_for(plan, plant, ref, config)
    items = shortlist(plan, records, [], [], run_id=RUN, plant=plant, ref=ref, caps=config.caps)
    by_target = {i.target_id: i for i in items}
    assert set(by_target) == {f.id for f in findings}  # never dropped
    assert by_target[rated.id].lopa is not None and by_target[rated.id].no_lopa_reason is None
    assert by_target[no_severity.id].lopa is None
    assert by_target[no_severity.id].no_lopa_reason == "no severity"
    assert HIGH_SEVERITY_NO_LOPA not in by_target[no_severity.id].flags
    high = by_target[no_frequency.id]
    assert high.lopa is None
    assert high.no_lopa_reason is not None and high.no_lopa_reason.startswith("no likelihood")
    assert HIGH_SEVERITY_NO_LOPA in high.flags


def test_code_only_lopa_outside_the_top_n_only_for_s4_s5(
    plant: Plant, ref: ReferenceSet, config: Config
) -> None:
    top = finding("pair:KOH:SIH", ["BLDG-1"], cause_text="top", severity=SeverityClass.S5)
    high = finding("env:SIH:water", ["BLDG-1"], cause_text="high", severity=SeverityClass.S4)
    low = finding("env:SIH:air", ["BLDG-1"], cause_text="low", severity=SeverityClass.S3)
    findings = [top, high, low]
    questions = [question(f.question_id) for f in findings]
    lines = display_lines(findings, [], questions, [], plant, ref, config.caps)
    plan = {p.target_id: p for p in lopa_plan(lines, [], findings, questions, [], top_n=1)}
    assert plan[top.id].kind == "full"
    assert plan[high.id].kind == "code_only"
    assert plan[low.id].kind == "none" and "outside the top 1" in (plan[low.id].reason or "")
    record = records_for([plan[high.id]], plant, ref, config)[0]
    assert CODE_ONLY_FLAG in record.flags


def test_shortlist_is_tier_then_gap_and_incomplete_after_complete(
    plant: Plant, ref: ReferenceSet, config: Config
) -> None:
    small = finding("pair:KOH:SIH", ["BLDG-1"], cause_text="a", severity=SeverityClass.S2)
    big = finding("env:SIH:water", ["BLDG-1"], cause_text="b", severity=SeverityClass.S5)
    findings = [small, big]
    questions = [question(f.question_id) for f in findings]
    lines = display_lines(findings, [], questions, [], plant, ref, config.caps)
    plan = lopa_plan(lines, [], findings, questions, [], top_n=10)
    records = records_for(plan, plant, ref, config)
    items = shortlist(plan, records, [], [], run_id=RUN, plant=plant, ref=ref, caps=config.caps)
    assert [i.target_id for i in items] == [big.id, small.id]
    assert all(not isinstance(i.lopa, NoLopa) for i in items)


def test_fact_ids_come_from_the_plant(plant: Plant) -> None:
    facts = {f.id for f in plant_facts(plant, "plant:x")}
    assert "MX-1.design_pressure_kpa" in facts


def test_the_high_severity_no_lopa_flag_reads_as_written() -> None:
    from guideword.lopa.lines import HIGH_SEVERITY_NO_LOPA  # noqa: PLC0415

    assert HIGH_SEVERITY_NO_LOPA == "S4–S5 with no LOPA — engineer to review"
