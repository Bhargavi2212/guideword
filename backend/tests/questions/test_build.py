"""The question builder (spec 1.4; plan P4, P9, Q4, Q5)."""

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from guideword.questions.build import build_questions, within_reach
from guideword.reference import ReferenceSet, load_reference_set
from guideword.schema import ids
from guideword.schema.enums import (
    QuestionKind,
    QuestionOrigin,
    QuestionStatus,
    SectionKind,
    SectionType,
)
from guideword.schema.plant import Plant
from guideword.schema.records import Question, Section
from guideword.sections.rules import rule_cut

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
RECORD = "plant:example_mixing_unit:0"
RUN = "run:test"


@pytest.fixture(scope="module")
def ref() -> ReferenceSet:
    return load_reference_set()


def _example() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    return data


def _build(data: dict[str, Any], ref: ReferenceSet) -> list[Question]:
    plant = Plant.model_validate(data)
    return build_questions(plant, rule_cut(plant, RECORD), ref, RUN)


def _by_id(data: dict[str, Any], ref: ReferenceSet) -> dict[str, Question]:
    return {q.id: q for q in _build(data, ref)}


def _rows(ref: ReferenceSet, section_type: str) -> int:
    return sum(1 for row in ref.applicability if row.section_type == section_type)


def _reach(data: dict[str, Any], job_id: str) -> list[str]:
    plant = Plant.model_validate(data)
    job = next(w for w in plant.planned_work if w.id == job_id)
    return within_reach(plant, job)


def _job(job_id: str, **fields: Any) -> dict[str, Any]:
    return {"id": job_id, "type": "hot_work", **fields}


# --- the §9 example ---------------------------------------------------------------------------


def test_example_counts_per_list(ref: ReferenceSet) -> None:
    counts = Counter(q.kind for q in _build(_example(), ref))
    # matrix = mixer rows + pump rows + tank rows + 4 pipe parts x pipe rows
    mixer, pump, tank, pipe = (_rows(ref, t) for t in ("mixer", "pump", "tank", "pipe"))
    assert (mixer, pump, tank, pipe) == (13, 7, 11, 12)
    assert counts[QuestionKind.MATRIX] == mixer + pump + tank + 4 * pipe == 79
    # 2 chemicals: 2 * 1 / 2 pairs, 3 * 2 environment questions
    assert counts[QuestionKind.CHEMICAL_PAIR] == 1
    assert counts[QuestionKind.CHEMICAL_ENVIRONMENT] == 6
    # both lines flow
    assert counts[QuestionKind.NO_FLOW_LINE] == 0
    # 2 steps x 5 procedure guidewords
    assert counts[QuestionKind.PROCEDURE_STEP] == 2 * 5 == 10
    # W-1 on ROOF reaches PSV-1, which discharges to ROOF (P9)
    assert counts[QuestionKind.PLANNED_WORK] == 1
    assert counts[QuestionKind.DUST] == 0
    assert counts[QuestionKind.RELIEF_DISCHARGE] == 1
    assert sum(counts.values()) == 79 + 1 + 6 + 0 + 10 + 1 + 0 + 1 == 98


def test_example_work_question_is_the_relief_device_on_the_roof(ref: ReferenceSet) -> None:
    work = [q.id for q in _build(_example(), ref) if q.kind == QuestionKind.PLANNED_WORK]
    assert work == ["work:W-1:PSV-1"]


def test_every_question_is_open_with_the_run_id_and_origin(ref: ReferenceSet) -> None:
    for q in _build(_example(), ref):
        assert q.status == QuestionStatus.OPEN
        assert q.run_id == RUN
        assert q.fact_ids == []
        expected = (
            QuestionOrigin.MATRIX if q.kind == QuestionKind.MATRIX else QuestionOrigin.CROSS_LIST
        )
        assert q.origin == expected


def test_order_is_list_order_then_id(ref: ReferenceSet) -> None:
    order = list(QuestionKind)
    questions = _build(_example(), ref)
    keys = [(order.index(q.kind), q.id) for q in questions]
    assert keys == sorted(keys)


def test_matrix_text(ref: ReferenceSet) -> None:
    q = _by_id(_example(), ref)["m:S-MX-1:more:pressure"]
    assert q.text == (
        "More pressure in S-MX-1 (mixer): what could cause it, what would happen, "
        "and is the existing protection adequate?"
    )


# --- chemical lists ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("n", "pairs", "environment"), [(0, 0, 0), (1, 0, 3), (2, 1, 6), (10, 45, 30)]
)
def test_chemical_counts(ref: ReferenceSet, n: int, pairs: int, environment: int) -> None:
    data = {
        "plant_id": "chem_only",
        "schema_version": "1.0",
        "chemicals": [{"id": f"C-{i:02d}", "name": f"chemical {i}"} for i in range(n)],
    }
    counts = Counter(q.kind for q in _build(data, ref))
    assert counts[QuestionKind.CHEMICAL_PAIR] == pairs == n * (n - 1) // 2
    assert counts[QuestionKind.CHEMICAL_ENVIRONMENT] == environment == 3 * n


def test_pair_ids_are_sorted_and_environment_covers_water_air_heat(ref: ReferenceSet) -> None:
    questions = _by_id(_example(), ref)
    assert "pair:KOH:SIH" in questions
    assert {f"env:SIH:{e}" for e in ("water", "air", "heat")} <= questions.keys()


# --- no-flow lines and procedures ------------------------------------------------------------


def test_no_flow_line_gets_pipe_matrix_plus_one_nf(ref: ReferenceSet) -> None:
    data = _example()
    data["lines"][0]["no_flow"] = ["normally_closed"]
    assert data["lines"][0]["id"] == "L-12"
    questions = _build(data, ref)
    l12 = [q for q in questions if q.section_id == "S-L-12"]
    matrix = [q for q in l12 if q.kind == QuestionKind.MATRIX]
    assert len(matrix) == _rows(ref, "pipe")
    assert [q.id for q in questions if q.kind == QuestionKind.NO_FLOW_LINE] == ["nf:L-12"]


def test_procedure_steps_times_five_and_never_before_or_after(ref: ReferenceSet) -> None:
    proc = [q for q in _build(_example(), ref) if q.kind == QuestionKind.PROCEDURE_STEP]
    assert len(proc) == 2 * len(ref.procedure_guidewords) == 10
    guidewords = {ids.parse_question_id(q.id).parts[1] for q in proc}
    assert guidewords == {"early", "late", "skipped", "wrong", "out_of_order"}
    assert not {"before", "after"} & guidewords


# --- within reach -----------------------------------------------------------------------------


def test_reach_listed_equipment_and_lines() -> None:
    data = _example()
    data["planned_work"].append(_job("W-2", equipment_ids=["TOTE-1"], line_ids=["L-12"]))
    assert _reach(data, "W-2") == ["L-12", "TOTE-1"]


def test_reach_equipment_in_location() -> None:
    data = _example()
    data["planned_work"].append(_job("W-2", location_id="BLDG-1"))
    assert {"MX-1", "P-1", "TOTE-1"} <= set(_reach(data, "W-2"))


def test_reach_lines_by_endpoint_in_location() -> None:
    """L-12 starts at TOTE-1 and L-STM at the utility UT-STEAM, both in BLDG-1."""
    data = _example()
    data["planned_work"].append(_job("W-2", location_id="BLDG-1"))
    assert _reach(data, "W-2") == ["L-12", "L-STM", "MX-1", "P-1", "TOTE-1"]


def test_reach_line_ending_at_the_location_itself() -> None:
    data = _example()
    data["lines"].append({"id": "L-VENT", "from_id": "MX-1", "to_id": "ROOF"})
    assert "L-VENT" in _reach(data, "W-1")


def test_reach_relief_device_discharging_at_the_location() -> None:
    assert _reach(_example(), "W-1") == ["PSV-1"]


def test_reach_overlapping_job() -> None:
    data = _example()
    data["planned_work"].append(
        _job("W-2", location_id="ROOF", start="2026-10-20T15:00:00", end="2026-10-20T17:00:00")
    )
    assert "W-2" in _reach(data, "W-1")
    assert "W-1" in _reach(data, "W-2")


def test_reach_non_overlapping_job_excluded() -> None:
    data = _example()
    data["planned_work"].append(
        _job("W-2", location_id="ROOF", start="2026-10-20T17:00:00", end="2026-10-20T18:00:00")
    )
    assert "W-2" not in _reach(data, "W-1")


def test_touching_windows_overlap() -> None:
    """Q4: a.start <= b.end and b.start <= a.end."""
    data = _example()
    data["planned_work"].append(
        _job("W-2", location_id="ROOF", start="2026-10-20T16:00:00", end="2026-10-20T18:00:00")
    )
    assert "W-2" in _reach(data, "W-1")


def test_reach_job_without_window_included() -> None:
    data = _example()
    data["planned_work"].append(_job("W-2", location_id="ROOF"))
    assert "W-2" in _reach(data, "W-1")
    assert "W-1" in _reach(data, "W-2")


def test_time_zone_mismatch_counts_as_overlap() -> None:
    data = _example()
    data["planned_work"].append(
        _job(
            "W-2",
            location_id="ROOF",
            start="2026-10-21T17:00:00+00:00",
            end="2026-10-21T18:00:00+00:00",
        )
    )
    assert "W-2" in _reach(data, "W-1")


def test_job_at_another_location_is_not_in_reach() -> None:
    data = _example()
    data["planned_work"].append(_job("W-2", location_id="BLDG-1"))
    assert "W-2" not in _reach(data, "W-1")


def test_unlocated_jobs_never_reach_each_other(ref: ReferenceSet) -> None:
    """P4: two unknowns are not the same location."""
    data = _example()
    data["planned_work"] += [_job("W-3"), _job("W-4")]
    assert _reach(data, "W-3") == []
    questions = _by_id(data, ref)
    assert {"work:W-3:W-3", "work:W-4:W-4"} <= questions.keys()
    assert "work:W-3:W-4" not in questions


def test_reach_empty_gives_job_itself(ref: ReferenceSet) -> None:
    data = _example()
    data["planned_work"].append(_job("W-3"))
    work = [q.id for q in _build(data, ref) if q.id.startswith("work:W-3:")]
    assert work == ["work:W-3:W-3"]


# --- dust and relief --------------------------------------------------------------------------


def _with_dust(data: dict[str, Any]) -> dict[str, Any]:
    data["chemicals"].append({"id": "FLOUR", "name": "flour", "combustible_dust": True})
    data["equipment"] += [
        {"id": "D-1", "type": "dryer", "location_id": "BLDG-1", "contents": ["FLOUR"]},
        {"id": "SH-1", "type": "solids_handler", "location_id": "BLDG-1"},
        {"id": "MX-2", "type": "mixer", "location_id": "BLDG-1", "contents": ["FLOUR", "SIH"]},
    ]
    return data


def test_dust_dryer_with_combustible_dust_once(ref: ReferenceSet) -> None:
    dust = [q.id for q in _build(_with_dust(_example()), ref) if q.kind == QuestionKind.DUST]
    assert dust == ["dust:D-1", "dust:MX-2", "dust:SH-1"]


def test_relief_question_section_is_protected_equipment(ref: ReferenceSet) -> None:
    assert _by_id(_example(), ref)["relief:PSV-1"].section_id == "S-MX-1"


def test_relief_on_a_pump_goes_to_its_equipment_section(ref: ReferenceSet) -> None:
    """Q5: P-1 is in S-P-1 and in the line part S-L-12~P-1; the equipment section wins."""
    data = _example()
    data["relief_devices"].append({"id": "PSV-2", "protects_id": "P-1"})
    assert _by_id(data, ref)["relief:PSV-2"].section_id == "S-P-1"


def test_several_qualifying_sections_take_the_lowest_id(ref: ReferenceSet) -> None:
    plant = Plant.model_validate(_example())
    sections = rule_cut(plant, RECORD)
    extra = Section(
        id="S-AAA",
        plant_record_id=RECORD,
        kind=SectionKind.EQUIPMENT,
        section_type=SectionType.MIXER,
        name="AAA",
        object_ids=["MX-1"],
        drawn_by="rule",
    )
    questions = {q.id: q for q in build_questions(plant, [*sections, extra], ref, RUN)}
    assert questions["relief:PSV-1"].section_id == "S-AAA"


def test_section_of_each_question_kind(ref: ReferenceSet) -> None:
    data = _with_dust(_example())
    data["lines"][0]["no_flow"] = ["dead_leg"]
    questions = _by_id(data, ref)
    assert questions["m:S-TOTE-1:more:level"].section_id == "S-TOTE-1"
    assert questions["nf:L-12"].section_id == "S-L-12"
    assert questions["proc:P-CHARGE-1:skipped"].section_id == "S-P-CHARGE"
    assert questions["work:W-1:PSV-1"].section_id == "S-W-1"
    assert questions["dust:D-1"].section_id == "S-D-1"
    assert questions["relief:PSV-1"].section_id == "S-MX-1"
    assert questions["pair:KOH:SIH"].section_id is None
    assert questions["env:KOH:water"].section_id is None


def test_question_with_no_qualifying_section_has_none(ref: ReferenceSet) -> None:
    plant = Plant.model_validate(_example())
    sections = [s for s in rule_cut(plant, RECORD) if s.id != "S-MX-1"]
    questions = {q.id: q for q in build_questions(plant, sections, ref, RUN)}
    assert questions["relief:PSV-1"].section_id is None


# --- IDs and text ------------------------------------------------------------------------------


def test_every_id_parses_no_duplicates_sections_exist(ref: ReferenceSet) -> None:
    data = _with_dust(_example())
    plant = Plant.model_validate(data)
    sections = rule_cut(plant, RECORD)
    questions = build_questions(plant, sections, ref, RUN)
    section_ids = {s.id for s in sections}
    assert len({q.id for q in questions}) == len(questions)
    for q in questions:
        assert ids.parse_question_id(q.id).kind == q.kind
        assert q.section_id is None or q.section_id in section_ids


def test_templates_never_include_note_text(ref: ReferenceSet) -> None:
    marker = "ZZ-NOTE-MARKER"
    data = _with_dust(_example())
    data["notes"] = [{"text": marker, "source": "pkg"}]
    for key in ("equipment", "lines", "chemicals", "procedures", "planned_work", "relief_devices"):
        for obj in data[key]:
            obj["notes"] = [{"text": marker, "source": "pkg"}]
    for step in data["procedures"][0]["steps"]:
        step["notes"] = [{"text": marker, "source": "pkg"}]
    data["lines"][0]["no_flow"] = ["standby"]
    for q in _build(data, ref):
        assert marker not in q.text


def test_templates_never_include_step_text(ref: ReferenceSet) -> None:
    for q in _build(_example(), ref):
        assert "Select tote by label" not in q.text
