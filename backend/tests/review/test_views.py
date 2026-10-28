"""The shortlist and worksheet views, overrides applied on read (spec 3.3, 3.5; Phase 3 plan
PR 6, Q14, G6, G9, G15). Pure: records built here, LOPA from the real engine."""

import math

import pytest

from guideword.config import Config
from guideword.lopa.engine import lopa_record
from guideword.lopa.lines import INCOMPLETE_LOPA, display_lines, lopa_plan
from guideword.reference import ReferenceSet
from guideword.review.display import frequency_text, gap_text
from guideword.review.overrides import RunRecords
from guideword.review.shortlist import RunView, shortlist_items
from guideword.review.worksheet import worksheet_rows
from guideword.schema import ids
from guideword.schema.enums import (
    Adequacy,
    Confidence,
    FailingComponentType,
    OverrideAction,
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
    Override,
    Question,
    Recommendation,
)

from .conftest import RUN, override

TOP_N = 10


def question(qid: str, status: QuestionStatus = QuestionStatus.ANSWERED) -> Question:
    return Question(
        id=qid,
        run_id=RUN,
        kind=ids.parse_question_id(qid).kind,
        origin=QuestionOrigin.CROSS_LIST,
        status=status,
        text=f"question {qid}",
        not_credible_reason="no path" if status == QuestionStatus.NOT_CREDIBLE else None,
    )


def finding(
    qid: str,
    components: list[str],
    severity: SeverityClass,
    *,
    cause_id: str | None = None,
    cause_text: str | None = None,
    kind: FailingComponentType = FailingComponentType.EXTERNAL,
    confidence: Confidence = Confidence.SURE,
    safeguards: list[str] | None = None,
) -> Finding:
    return Finding(
        id=ids.finding_id(
            qid, Tier.LIGHTNING, components, cause_id=cause_id, cause_text=cause_text
        ),
        run_id=RUN,
        question_id=qid,
        tier=Tier.LIGHTNING,
        cause_id=cause_id or OUTSIDE_LIBRARY,
        cause_text=cause_text,
        failing_component_type=kind,
        failing_component_ids=components,
        consequence=f"consequence of {cause_text or cause_id}",
        safeguard_ids=safeguards or [],
        adequacy=Adequacy.UNKNOWN,
        confidence=confidence,
        severity_class=severity,
        severity_reason="test",
    )


class Case:
    """Three tiers: a confirmed S3 line, then also-found lines (S5, S2, an incomplete S4 C20
    leak on L-12, which has no length), then an unconfirmed hypothesis; one chain."""

    def __init__(self, plant: Plant, ref: ReferenceSet, config: Config) -> None:
        self.plant, self.ref, self.config = plant, ref, config
        self.confirmed = finding("env:SIH:water", ["BLDG-1"], SeverityClass.S3, cause_text="conf")
        self.big = finding(
            "env:KOH:water", ["BLDG-1"], SeverityClass.S5, cause_text="big", safeguards=["SG-TRIP"]
        )
        self.low = finding(
            "pair:KOH:SIH",
            ["BLDG-1"],
            SeverityClass.S2,
            cause_text="low",
            confidence=Confidence.UNSURE,
        )
        self.folded = finding("env:KOH:air", ["BLDG-1"], SeverityClass.S2, cause_text="low")
        self.leak = finding(
            "env:SIH:air",
            ["L-12"],
            SeverityClass.S4,
            cause_id="C20",
            kind=FailingComponentType.PIPE,
        )
        self.findings = [self.confirmed, self.big, self.low, self.folded, self.leak]
        self.questions = [question(f.question_id) for f in self.findings] + [
            question("env:SIH:heat", QuestionStatus.NOT_CREDIBLE)
        ]
        self.hypothesis = Hypothesis(
            id=ids.hypothesis_id(1, "conf", ["BLDG-1"]),
            run_id=RUN,
            rank=1,
            mechanism="conf",
            component_ids=["BLDG-1"],
            failing_component_type=FailingComponentType.EXTERNAL,
            cause_id=OUTSIDE_LIBRARY,
            cause_text="conf",
            consequence="c",
            reason="r",
            question_ids=[self.confirmed.question_id],
        )
        self.unconfirmed = Hypothesis(
            id=ids.hypothesis_id(2, "nothing", ["MX-1"]),
            run_id=RUN,
            rank=2,
            mechanism="nothing",
            component_ids=["MX-1"],
            failing_component_type=FailingComponentType.EXTERNAL,
            cause_id=OUTSIDE_LIBRARY,
            cause_text="nothing",
            consequence="c",
            reason="r",
            question_ids=["env:KOH:heat"],
        )
        links = [self.big.id, self.low.id]
        self.chain = Chain(
            id=ids.chain_id(links),
            run_id=RUN,
            links=links,
            description="one then the other",
            reason="r",
            severity_class=SeverityClass.S4,
            severity_reason="two hurt",
        )
        hypotheses = [self.hypothesis, self.unconfirmed]
        lines = display_lines(
            self.findings, hypotheses, self.questions, [], plant, ref, config.caps
        )
        plan = lopa_plan(lines, [self.chain], self.findings, self.questions, [], top_n=TOP_N)
        self.records: list[LopaRecord] = []
        for p in plan:
            if p.scenario is not None:
                found = lopa_record(
                    p.scenario, run_id=RUN, plant=plant, ref=ref, caps=config.caps, arguments=None
                )
                if isinstance(found, LopaRecord):
                    self.records.append(found)
        self.rec = Recommendation(
            id=ids.recommendation_id(self.big.id, "add a deluge"),
            run_id=RUN,
            target_id=self.big.id,
            action="add a deluge",
            reason="r",
            model_call_id="mc:rec",
        )
        self.hypotheses = hypotheses

    def view(self, overrides: list[Override] | None = None) -> RunView:
        return RunView(
            run_id=RUN,
            top_n=TOP_N,
            pre_r50=False,
            records=RunRecords(
                findings=self.findings,
                chains=[self.chain],
                lopa_records=self.records,
                recommendations=[self.rec],
                questions=self.questions,
                sections=[],
                overrides=overrides or [],
            ),
            hypotheses=self.hypotheses,
            model_calls=[],
        )

    def items(self, overrides: list[Override] | None = None) -> list:
        return shortlist_items(self.view(overrides), self.plant, self.ref, self.config.caps)

    def lopa_of(self, target_id: str) -> LopaRecord:
        return next(r for r in self.records if r.target_id == target_id)


@pytest.fixture
def case(plant: Plant, ref: ReferenceSet, config: Config) -> Case:
    return Case(plant, ref, config)


TIERS = [ShortlistTier.CONFIRMED, ShortlistTier.ALSO_FOUND, ShortlistTier.UNCONFIRMED]


def _bucket(item) -> int:  # type: ignore[no-untyped-def]
    if item.lopa is not None and item.lopa.complete:
        return 0
    return 1 if item.lopa is not None else 2


def _assert_ordered(items: list) -> None:
    keys = [(TIERS.index(i.tier), _bucket(i)) for i in items]
    assert keys == sorted(keys)
    for a, b in zip(items, items[1:], strict=False):
        if (a.tier, _bucket(a)) == (b.tier, _bucket(b)) == (a.tier, 0):
            assert a.gap >= b.gap


# --- the shortlist (3.3) ----------------------------------------------------------------------


def test_shortlist_order_is_tier_then_gap_and_gap_never_crosses_tiers(case: Case) -> None:
    items = case.items()
    assert [i.rank for i in items] == list(range(1, len(items) + 1))
    _assert_ordered(items)
    assert items[0].target_id == case.confirmed.id and items[0].tier == ShortlistTier.CONFIRMED
    big_gap = case.lopa_of(case.big.id).gap
    assert big_gap is not None and items[0].gap is not None and items[0].gap < big_gap
    # the engineer lowers the confirmed line to S1: it stays first; lowering the S5 line
    # below the S2 line's gap reorders the also-found tier only
    overrides = [
        override(case.confirmed.id, OverrideAction.CHANGE_SEVERITY, {"severity_class": "S1"}),
        override(case.big.id, OverrideAction.CHANGE_SEVERITY, {"severity_class": "S1"}),
    ]
    again = case.items(overrides)
    _assert_ordered(again)
    assert again[0].target_id == case.confirmed.id
    order = [i.target_id for i in again]
    low_line = next(t for t in order if t in (case.low.id, case.folded.id))
    assert order.index(low_line) < order.index(case.big.id)
    lowered = next(i for i in again if i.target_id == case.big.id)
    assert lowered.finding.severity_class == SeverityClass.S1
    assert lowered.lopa.severity_class == SeverityClass.S1
    assert case.big.severity_class == SeverityClass.S5  # the record is unchanged


def test_incomplete_lopa_after_complete_within_a_tier(case: Case) -> None:
    items = case.items()
    also = [i for i in items if i.tier == ShortlistTier.ALSO_FOUND]
    leak = next(i for i in also if i.target_id == case.leak.id)
    assert leak.lopa is not None and not leak.lopa.complete and leak.gap is None
    assert INCOMPLETE_LOPA in leak.flags
    complete = [i for i in also if i.lopa is not None and i.lopa.complete]
    assert complete and also.index(leak) > max(also.index(i) for i in complete)


def test_shortlist_items_carry_their_records_flags_and_unsure(case: Case) -> None:
    items = {i.target_id: i for i in case.items()}
    big = items[case.big.id]
    assert big.recommendations == [case.rec] and big.finding == case.big
    chain = items[case.chain.id]
    assert chain.target_kind == "chain" and chain.chain == case.chain and chain.lopa is not None
    # G9: a chain is unsure when any finding link is
    assert chain.unsure is True and big.unsure is False
    unconfirmed = items[case.unconfirmed.id]
    assert unconfirmed.target_kind == "hypothesis" and unconfirmed.tier == ShortlistTier.UNCONFIRMED
    assert any("no LOPA" in flag for flag in unconfirmed.flags)
    confirmed = items[case.confirmed.id]
    assert confirmed.hypothesis_id == case.hypothesis.id and confirmed.support_finding_ids


def test_a_rejected_row_stays_listed_as_rejected_in_both_views(case: Case) -> None:
    rejected = override(case.big.id, OverrideAction.REJECT, None)
    rejected_rec = override(case.rec.id, OverrideAction.REJECT, None)
    items = {i.target_id: i for i in case.items([rejected, rejected_rec])}
    big = items[case.big.id]
    assert any("rejected" in flag and rejected.id in flag for flag in big.flags)
    assert big.recommendations == [case.rec]
    assert any(case.rec.id in flag and "rejected" in flag for flag in big.flags)
    rows = {
        r.row_id: r
        for r in worksheet_rows(case.view([rejected]), case.plant, case.ref, case.config.caps)
    }
    assert rows[case.big.id].override_state == "rejected"


def test_overrides_applied_on_read_and_model_records_unchanged(case: Case) -> None:
    before = [f.model_dump() for f in case.findings], [r.model_dump() for r in case.records]
    edit = override(case.big.id, OverrideAction.EDIT, {"consequence": "the hall floods"})
    lopa = case.lopa_of(case.big.id)
    items = {i.target_id: i for i in case.items([edit])}
    assert items[case.big.id].finding.consequence == "the hall floods"
    rows = {
        r.row_id: r
        for r in worksheet_rows(case.view([edit]), case.plant, case.ref, case.config.caps)
    }
    assert rows[case.big.id].consequences == "the hall floods"
    assert rows[case.big.id].override_state == "edited" and edit.id in rows[case.big.id].record_ids
    assert (
        [f.model_dump() for f in case.findings],
        [r.model_dump() for r in case.records],
    ) == before
    assert lopa.target_id == case.big.id


# --- the worksheet (Q14, G15) ------------------------------------------------------------------


def test_worksheet_has_one_row_per_finding_and_per_question_without_one(case: Case) -> None:
    rows = worksheet_rows(case.view(), case.plant, case.ref, case.config.caps)
    ids_ = [r.row_id for r in rows]
    assert sorted(ids_) == sorted([*(f.id for f in case.findings), "env:SIH:heat"])
    by_id = {r.row_id: r for r in rows}
    dismissed = by_id["env:SIH:heat"]
    assert dismissed.status == "not credible" and dismissed.causes == "no path"
    assert dismissed.record_ids == ["env:SIH:heat"]
    big = by_id[case.big.id]
    assert big.origin == "cross_list"
    assert big.existing_safeguards == "SG-TRIP"  # the example plant gives no description
    described = case.plant.model_copy(
        update={
            "safeguards": [
                g.model_copy(update={"description": "high-temperature trip"})
                if g.id == "SG-TRIP"
                else g
                for g in case.plant.safeguards
            ]
        }
    )
    rows_described = worksheet_rows(case.view(), described, case.ref, case.config.caps)
    shown = next(r for r in rows_described if r.row_id == case.big.id)
    assert shown.existing_safeguards == "SG-TRIP: high-temperature trip"
    assert big.severity == "S5" and big.recommendation == "add a deluge"
    assert ids.lopa_id(case.big.id) in big.record_ids and case.rec.id in big.record_ids
    assert by_id[case.low.id].status == "answered (unsure)"
    # Q14: the folded member shows the line's LOPA gap, marked "(scenario)"
    low, folded = by_id[case.low.id], by_id[case.folded.id]
    assert folded.lopa_gap == low.lopa_gap and folded.lopa_gap is not None
    assert folded.lopa_gap.endswith("(scenario)")
    assert by_id[case.leak.id].lopa_gap == "incomplete: L-12.length_m missing"


def test_gap_is_shown_as_an_order_of_magnitude(case: Case) -> None:
    assert frequency_text(1e-4) == "about 1 in 10,000 years"
    assert frequency_text(2e-5) == "about 1 in 100,000 years"
    assert frequency_text(3.2e-5) == "about 1 in 10,000 years"  # nearer 1e-4 in log terms
    assert frequency_text(0.5) == "about 1 per year"
    assert frequency_text(20.0) == "about 10 per year"
    record = case.lopa_of(case.big.id)
    assert record.gap is not None and record.mitigated_frequency_per_year is not None
    text = gap_text(record)
    magnitude = 10 ** round(math.log10(record.gap))
    assert text.startswith(f"about {magnitude:,}× tolerable")
    assert frequency_text(record.mitigated_frequency_per_year) in text
    assert frequency_text(record.tolerable_per_year) in text
    rows = {
        r.row_id: r for r in worksheet_rows(case.view(), case.plant, case.ref, case.config.caps)
    }
    assert rows[case.big.id].lopa_gap == text
    # the stored numbers are not rounded
    assert record.gap != magnitude or record.gap == float(magnitude)


def test_card_gap_text_is_the_worksheet_text_for_the_same_line(case: Case) -> None:
    """Bhargavi, 2026-10-20 (PR 6 answer 2): one formatter writes the gap for the card
    (`gap_text`, contract v1.6) and the worksheet, so the two can never disagree."""
    from guideword.review.worksheet import SCENARIO_MARK  # noqa: PLC0415

    items = case.items()
    rows = {
        r.row_id: r for r in worksheet_rows(case.view(), case.plant, case.ref, case.config.caps)
    }
    checked = 0
    for item in items:
        if item.lopa is None:
            assert item.gap_text is None
            continue
        assert item.gap_text == gap_text(item.lopa)
        if item.target_kind == "finding":
            shown = rows[item.target_id].lopa_gap
            assert shown is not None
            assert shown.removesuffix(SCENARIO_MARK) == item.gap_text
            checked += 1
    assert checked >= 2
    assert any(i.lopa is None and i.gap_text is None for i in items)


@pytest.mark.parametrize(
    ("gap", "times"),
    [
        (10.0, "about 10× tolerable"),
        (1000.0, "about 1,000× tolerable"),
        (0.01 / 1e-5, "about 1,000× tolerable"),  # 999.9999999999999 in floats
        (1.0, "within tolerable"),
        (1.5, "about 1× tolerable"),
    ],
)
def test_the_gap_text_at_its_boundaries(case: Case, gap: float, times: str) -> None:
    tolerable = 1e-5
    record = case.lopa_of(case.big.id).model_copy(
        update={
            "gap": gap,
            "tolerable_per_year": tolerable,
            "mitigated_frequency_per_year": gap * tolerable,
        }
    )
    assert gap_text(record).startswith(f"{times} — mitigated ")


# --- unexpected characters in model text (Bhargavi, 2026-10-22) --------------------------------


def test_a_chain_with_an_unexpected_character_is_flagged_and_kept_as_written(case: Case) -> None:
    case.chain = case.chain.model_copy(update={"description": case.chain.description + "互"})
    item = next(i for i in case.items() if i.target_kind == "chain")
    assert "unexpected character in model text: U+4E92 (chain description)" in item.flags
    assert item.chain is not None and item.chain.description.endswith("互")


def test_a_finding_with_an_unexpected_character_is_flagged(case: Case) -> None:
    lead = next(i for i in case.items() if i.target_kind == "finding" and i.finding is not None)
    assert lead.finding is not None
    case.findings = [
        f.model_copy(update={"consequence": f.consequence + "水。"})
        if f.id == lead.target_id
        else f
        for f in case.findings
    ]
    item = next(i for i in case.items() if i.target_id == lead.target_id)
    assert "unexpected character in model text: U+6C34 (finding consequence)" in item.flags
    assert "unexpected character in model text: U+3002 (finding consequence)" in item.flags
    assert item.finding is not None and item.finding.consequence.endswith("水。")


# --- model text with no closing punctuation (Bhargavi, 2026-10-28: F6 defect 7) ---------------


def test_a_chain_cut_off_mid_sentence_is_flagged_and_kept_as_written(case: Case) -> None:
    cut = case.chain.description.rstrip(".") + " and the"
    case.chain = case.chain.model_copy(update={"description": cut})
    item = next(i for i in case.items() if i.target_kind == "chain")
    assert "text ends mid-sentence as stored (chain description)" in item.flags
    assert item.chain is not None and item.chain.description == cut


def test_a_chain_that_ends_its_sentence_has_no_such_flag(case: Case) -> None:
    case.chain = case.chain.model_copy(update={"description": "The shell is isolated."})
    item = next(i for i in case.items() if i.target_kind == "chain")
    assert "text ends mid-sentence as stored (chain description)" not in item.flags
