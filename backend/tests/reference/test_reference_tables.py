"""The shipped reference tables pass every spec 0.6 acceptance check."""

import csv
from pathlib import Path

import pytest

from guideword.reference import FROZEN_HEADERS, ReferenceSet, load_reference_set
from guideword.schema.enums import (
    FailingComponentType,
    Guideword,
    LikelihoodClass,
    ReliefKind,
    RiskRating,
    SectionType,
    SeverityClass,
)

REPO_REFERENCE = Path(__file__).resolve().parents[3] / "reference"

# Typed out from spec 0.6 independently of the loader's constant.
SPEC_HEADERS = {
    "applicability.csv": "section_type,guideword,parameter,source",
    "causes.csv": "id,cause,applies_to,failing_component_type,initiating_event_id,source",
    "initiating_events.csv": "id,event,frequency,unit,source",
    "protection_layers.csv": (
        "id,layer,category,pfd,pfd_if_isolatable,requires_independent_sensor,"
        "requires_independent_logic,requires_independent_final_element,no_credit_if_isolated,"
        "scenarios,conditions_text,relief_kind,source"
    ),
    "modifiers.csv": (
        "id,kind,release_phase,release_rate_kg_s_band,area_occupancy,event_type,"
        "operating_pattern,value,source"
    ),
    "severity_classes.csv": "severity_class,name,definition,source",
    "tolerable_frequencies.csv": "severity_class,tolerable_per_year,source",
    "likelihood_classes.csv": "likelihood_class,name,min_per_year,max_per_year,source",
    "risk_matrix.csv": "severity_class,likelihood_class,rating,source",
    "cameo_groups.csv": "cameo_group_id,name,source",
    "reactive_groups.csv": "epa_group_id,name,do_not_mix,source",
    "reactive_pairs.csv": "group_a,group_b,codes,source",
}


@pytest.fixture(scope="module")
def ref() -> ReferenceSet:
    return load_reference_set(REPO_REFERENCE)


def test_loader_headers_match_the_spec() -> None:
    assert {k: ",".join(v) for k, v in FROZEN_HEADERS.items()} == SPEC_HEADERS


@pytest.mark.parametrize("name", sorted(SPEC_HEADERS))
def test_file_header_equals_frozen_header(name: str) -> None:
    first_line = (REPO_REFERENCE / name).read_bytes().split(b"\n", 1)[0].decode("utf-8")
    assert first_line == SPEC_HEADERS[name]


@pytest.mark.parametrize("name", sorted(SPEC_HEADERS))
def test_every_row_has_a_source(name: str) -> None:
    with (REPO_REFERENCE / name).open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows
    assert all(row["source"].strip() for row in rows)


@pytest.mark.parametrize("path", sorted(REPO_REFERENCE.iterdir()), ids=lambda p: p.name)
def test_no_carriage_returns(path: Path) -> None:
    assert b"\r" not in path.read_bytes()


def test_the_precedent_index_is_not_a_reference_set_table() -> None:
    """Phase 4 adds it outside the ReferenceSet (P4-9); its own tests are in
    test_precedent_index.py (it replaces test_no_precedent_index_yet, plan PR 3)."""
    assert (REPO_REFERENCE / "precedent_index.csv").exists()
    assert "precedent_index.csv" not in SPEC_HEADERS


def test_set_loads(ref: ReferenceSet) -> None:
    assert set(ref.versions) == set(SPEC_HEADERS)


# --- applicability ---------------------------------------------------------------------------


def test_applicability_every_section_type_has_a_row(ref: ReferenceSet) -> None:
    assert {row.section_type for row in ref.applicability} == set(SectionType)


def test_applicability_has_no_duplicates(ref: ReferenceSet) -> None:
    keys = [(r.section_type, r.guideword, r.parameter) for r in ref.applicability]
    assert len(keys) == len(set(keys))


def test_procedure_rows_are_the_five_procedure_guidewords(ref: ReferenceSet) -> None:
    assert ref.procedure_guidewords == (
        Guideword.EARLY,
        Guideword.LATE,
        Guideword.SKIPPED,
        Guideword.WRONG,
        Guideword.OUT_OF_ORDER,
    )
    assert set(ref.procedure_guidewords) == {
        Guideword.SKIPPED,
        Guideword.WRONG,
        Guideword.EARLY,
        Guideword.LATE,
        Guideword.OUT_OF_ORDER,
    }


# --- causes and initiating events -----------------------------------------------------------


def test_causes_reference_existing_events(ref: ReferenceSet) -> None:
    events = {e.id for e in ref.initiating_events}
    assert len(ref.causes) == 26
    assert len({c.id for c in ref.causes}) == len(ref.causes)
    assert all(c.initiating_event_id in events for c in ref.causes)
    assert all(isinstance(c.failing_component_type, FailingComponentType) for c in ref.causes)


def test_cause_applies_to_values(ref: ReferenceSet) -> None:
    allowed = {s.value for s in SectionType} | {"planned_work"}
    for cause in ref.causes:
        assert cause.applies_to
        assert set(cause.applies_to) <= allowed


def test_initiating_event_units(ref: ReferenceSet) -> None:
    units = {e.unit for e in ref.initiating_events}
    assert units == {"per_year", "per_opportunity", "per_metre_year", "per_lift"}
    assert all(e.frequency > 0 for e in ref.initiating_events)


def test_non_yearly_events_are_never_yearly_frequencies(ref: ReferenceSet) -> None:
    for event in ref.initiating_events:
        if event.unit == "per_year":
            assert event.frequency_per_year == event.frequency
        else:
            assert event.frequency_per_year is None
    assert ref.initiating_event("IE-PIPE-LEAK-S").frequency_per_year is None
    assert ref.initiating_event("IE-CRANE").frequency_per_year is None
    assert ref.initiating_event("IE-BPCS").frequency_per_year == 0.1


# --- protection layers and modifiers -------------------------------------------------------


def test_protection_layer_probabilities_and_flags(ref: ReferenceSet) -> None:
    assert len(ref.protection_layers) == 26
    for layer in ref.protection_layers:
        assert 0 < layer.pfd <= 1
        assert layer.pfd_if_isolatable is None or 0 < layer.pfd_if_isolatable <= 1


def test_each_relief_kind_is_on_exactly_one_row(ref: ReferenceSet) -> None:
    by_kind = {k: ref.layer_for_relief_kind(k).id for k in ReliefKind}
    assert by_kind == {
        ReliefKind.PRV: "IPL-PRV",
        ReliefKind.RUPTURE_DISK: "IPL-RD",
        ReliefKind.PRV_WITH_DISK: "IPL-PRV-RD",
        ReliefKind.VENT: "IPL-CONS-VENT",
    }
    assert sum(1 for layer in ref.protection_layers if layer.relief_kind) == 4


def test_modifier_values_are_probabilities(ref: ReferenceSet) -> None:
    assert len(ref.modifiers) == 15
    assert all(0 < m.value <= 1 for m in ref.modifiers)


# --- severity, tolerable, likelihood, risk matrix -----------------------------------------


def test_each_severity_class_once(ref: ReferenceSet) -> None:
    assert [r.severity_class for r in ref.severity_classes] == list(SeverityClass)
    assert [r.severity_class for r in ref.tolerable_frequencies] == list(SeverityClass)
    assert all(r.tolerable_per_year > 0 for r in ref.tolerable_frequencies)


def test_likelihood_bands_are_contiguous_from_zero_with_open_top(ref: ReferenceSet) -> None:
    bands = ref.likelihood_classes
    assert [b.likelihood_class for b in bands] == list(LikelihoodClass)
    assert bands[0].min_per_year == 0
    assert bands[-1].max_per_year is None
    for lower, upper in zip(bands, bands[1:], strict=False):
        assert lower.max_per_year == upper.min_per_year


def test_risk_matrix_has_every_pair_once(ref: ReferenceSet) -> None:
    pairs = [(r.severity_class, r.likelihood_class) for r in ref.risk_matrix]
    assert len(pairs) == 25
    assert set(pairs) == {(s, lk) for s in SeverityClass for lk in LikelihoodClass}
    assert all(isinstance(r.rating, RiskRating) for r in ref.risk_matrix)


def test_risk_matrix_rating_rule(ref: ReferenceSet) -> None:
    # S number + L number: 2-4 low, 5-6 medium, 7-8 high, 9-10 very_high (decision 2026-10-12).
    def expected(total: int) -> RiskRating:
        if total <= 4:
            return RiskRating.LOW
        if total <= 6:
            return RiskRating.MEDIUM
        if total <= 8:
            return RiskRating.HIGH
        return RiskRating.VERY_HIGH

    for row in ref.risk_matrix:
        total = int(row.severity_class[1]) + int(row.likelihood_class[1])
        assert row.rating == expected(total)


# --- reactive groups and pairs -------------------------------------------------------------


def test_reactive_groups(ref: ReferenceSet) -> None:
    assert len(ref.reactive_groups) == 41
    assert [g.epa_group_id for g in ref.reactive_groups if g.do_not_mix] == [107]


def test_reactive_pairs(ref: ReferenceSet) -> None:
    assert len(ref.reactive_pairs) == 303
    unordered = {frozenset((p.group_a, p.group_b)) for p in ref.reactive_pairs}
    assert len(unordered) == 303
    assert all(107 not in (p.group_a, p.group_b) for p in ref.reactive_pairs)


def test_listed_pair_is_found_in_either_order(ref: ReferenceSet) -> None:
    forward = ref.reactivity(105, 106)
    backward = ref.reactivity(106, 105)
    assert forward.status == backward.status == "listed"
    assert set(forward.codes) == {"GT", "GF"}
    assert forward.row is not None and forward.row.source


def test_missing_pair_is_not_listed_never_compatible(ref: ReferenceSet) -> None:
    result = ref.reactivity(10, 105)
    assert result.status == "not_listed"
    assert result.codes == ()
    assert result.row is None


def test_group_107_is_do_not_mix(ref: ReferenceSet) -> None:
    assert ref.reactivity(107, 1).status == "do_not_mix"
    assert ref.reactivity(4, 107).status == "do_not_mix"


def test_unknown_group_is_an_error(ref: ReferenceSet) -> None:
    with pytest.raises(KeyError):
        ref.reactivity(999, 1)


def test_cameo_groups(ref: ReferenceSet) -> None:
    ids = [g.cameo_group_id for g in ref.cameo_groups]
    assert len(ids) == 68
    assert len(set(ids)) == 68


# --- versions ---------------------------------------------------------------------------------


def test_version_hash_is_sha256_of_file_bytes(ref: ReferenceSet) -> None:
    import hashlib

    for name, version in ref.versions.items():
        assert version == hashlib.sha256((REPO_REFERENCE / name).read_bytes()).hexdigest()
