"""A confirmed line's lead tie-break (specs/phase-3-lead-tiebreak-plan.md, approved 2026-10-21).

Among supporting findings that tie on rating, severity, frequency and protection, prefer one
whose question's section contains a hypothesis component; then the finding ID as before.
Gated by `ranking.lead_prefers_own_section`, read from the run (its latest `run_extended`
event, else its stored caps), so runs stored without it read exactly as before."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from guideword.config import Config, load_config
from guideword.ranking.rank import rank_findings
from guideword.ranking.tiers import lead_prefers_own_section, tiered
from guideword.reference import ReferenceSet, load_reference_set
from guideword.schema import ids
from guideword.schema.enums import (
    Adequacy,
    Confidence,
    EventType,
    FailingComponentType,
    QuestionOrigin,
    QuestionStatus,
    SeverityClass,
    ShortlistTier,
    Tier,
)
from guideword.schema.plant import Plant
from guideword.schema.records import OUTSIDE_LIBRARY, Event, Finding, Hypothesis, Question
from guideword.sections.rules import rule_cut

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
RUN = "run:lead"
ENV_Q = "env:SIH:water"
OWN_Q = "m:S-MX-1:more:temperature"


@pytest.fixture(scope="module")
def ref() -> ReferenceSet:
    return load_reference_set()


@pytest.fixture(scope="module")
def config() -> Config:
    return load_config(global_budget_usd=25.0)


@pytest.fixture(scope="module")
def plant() -> Plant:
    return Plant.model_validate(json.loads(EXAMPLE.read_text(encoding="utf-8")))


def _question(qid: str, section_id: str | None) -> Question:
    return Question(
        id=qid,
        run_id=RUN,
        kind=ids.parse_question_id(qid).kind,
        origin=QuestionOrigin.MATRIX if qid.startswith("m:") else QuestionOrigin.CROSS_LIST,
        status=QuestionStatus.ANSWERED,
        section_id=section_id,
        text="q",
    )


def _finding(qid: str, severity: SeverityClass) -> Finding:
    return Finding(
        id=ids.finding_id(qid, Tier.SUPER, ["MX-1"], cause_text="hot"),
        run_id=RUN,
        question_id=qid,
        tier=Tier.SUPER,
        cause_id=OUTSIDE_LIBRARY,
        cause_text="hot",
        failing_component_type=FailingComponentType.EXTERNAL,
        failing_component_ids=["MX-1"],
        consequence="c",
        adequacy=Adequacy.UNKNOWN,
        confidence=Confidence.SURE,
        severity_class=severity,
        severity_reason="r",
    )


def _hypothesis() -> Hypothesis:
    return Hypothesis(
        id=ids.hypothesis_id(1, "heat", ["MX-1"]),
        run_id=RUN,
        rank=1,
        mechanism="heat",
        component_ids=["MX-1"],
        failing_component_type=FailingComponentType.EXTERNAL,
        cause_id=OUTSIDE_LIBRARY,
        cause_text="hot",
        consequence="c",
        reason="r",
        question_ids=[ENV_Q, OWN_Q],
    )


def _lead(plant: Plant, ref: ReferenceSet, config: Config, own: SeverityClass, flag: bool) -> str:
    sections = rule_cut(plant, "plant:x:0")
    assert any(s.id == "S-MX-1" and "MX-1" in s.object_ids for s in sections)
    findings = [_finding(ENV_Q, SeverityClass.S3), _finding(OWN_Q, own)]
    questions = [_question(ENV_Q, None), _question(OWN_Q, "S-MX-1")]
    ranked = rank_findings(findings, plant, ref, config.caps)
    lines = tiered(
        ranked, [_hypothesis()], findings, questions, sections=sections, prefer_own_section=flag
    )
    [confirmed] = [line for line in lines if line.tier == ShortlistTier.CONFIRMED]
    assert confirmed.lead is not None
    return confirmed.lead.finding.question_id


def test_a_tie_prefers_a_finding_from_the_hypotheses_own_section(
    plant: Plant, ref: ReferenceSet, config: Config
) -> None:
    # today the env finding leads on the ID ("f:env" sorts before "f:m")
    assert _lead(plant, ref, config, SeverityClass.S3, flag=False) == ENV_Q
    assert _lead(plant, ref, config, SeverityClass.S3, flag=True) == OWN_Q


def test_the_tie_break_never_outranks_severity_likelihood_or_protection(
    plant: Plant, ref: ReferenceSet, config: Config
) -> None:
    """An own-section S2 never leads an S3 (the demo's reboiler B line)."""
    assert _lead(plant, ref, config, SeverityClass.S2, flag=True) == ENV_Q


def test_ownership_the_fold_and_the_global_rank_are_unchanged(
    plant: Plant, ref: ReferenceSet, config: Config
) -> None:
    sections = rule_cut(plant, "plant:x:0")
    findings = [_finding(ENV_Q, SeverityClass.S3), _finding(OWN_Q, SeverityClass.S3)]
    questions = [_question(ENV_Q, None), _question(OWN_Q, "S-MX-1")]
    ranked = rank_findings(findings, plant, ref, config.caps)
    off = tiered(ranked, [_hypothesis()], findings, questions, sections=sections)
    on = tiered(
        ranked, [_hypothesis()], findings, questions, sections=sections, prefer_own_section=True
    )
    assert [line.tier for line in off] == [line.tier for line in on]
    assert set(off[0].support_ids) == set(on[0].support_ids)
    assert [r.finding.id for r in ranked] == [
        r.finding.id for r in rank_findings(findings, plant, ref, config.caps)
    ]


def _event(seq: int, payload: dict[str, object]) -> Event:
    return Event(
        run_id=RUN,
        seq=seq,
        type=EventType.RUN_EXTENDED,
        payload=payload,
        time=datetime(2026, 10, 21, tzinfo=UTC),
    )


def test_runs_stored_without_the_setting_read_exactly_as_before() -> None:
    """D–G (and the G2b E/F runs among them) store no such setting, and their `run_extended`
    events carry none: the rule stays off for them."""
    stored = json.loads(
        (REPO / "backend" / "tests" / "runs" / "fixtures" / "dev_run_inputs.json").read_text(
            encoding="utf-8"
        )
    )["runs"]
    for case in stored.values():
        caps = case["inputs"]["caps"]
        assert "lead_prefers_own_section" not in caps.get("ranking", {})
        assert lead_prefers_own_section(caps, []) is False
        assert lead_prefers_own_section(caps, [_event(5, {"settings": {}})]) is False
    # a re-run records the setting on its run_extended event; the latest one wins
    on = [_event(5, {"ranking": {"lead_prefers_own_section": True}})]
    assert lead_prefers_own_section({}, on) is True
    assert lead_prefers_own_section({"ranking": {"lead_prefers_own_section": True}}, []) is True


def test_new_runs_store_the_setting(config: Config) -> None:
    from guideword.runs.case import run_settings  # noqa: PLC0415

    assert run_settings(config).caps["ranking"]["lead_prefers_own_section"] is True
