"""Starting and resuming runs (spec 2.1; plan R21, R24)."""

from collections.abc import Callable
from dataclasses import replace

import pytest

from guideword.questions.build import build_questions
from guideword.reference import ReferenceSet
from guideword.runs.plants import PlantRepository
from guideword.runs.start import (
    ModeNotBuilt,
    PlantNotFound,
    RunSettings,
    SectionsNotConfirmed,
    start_run,
)
from guideword.runs.store import RunRepository
from guideword.schema import ids
from guideword.schema.enums import EventType, PlantStatus, RunLabelKind, RunStatus
from guideword.schema.records import Run
from guideword.sections.rules import rule_cut

Upload = Callable[..., str]


def _start(
    plants: PlantRepository,
    runs: RunRepository,
    ref: ReferenceSet,
    settings: RunSettings,
    plant_record_id: str,
    cap: float = 1.0,
    mode: str = "full",
) -> Run:
    return start_run(
        plants,
        runs,
        ref,
        settings,
        plant_record_id=plant_record_id,
        spend_cap_usd=cap,
        mode=mode,
    )


def _set_status(runs: RunRepository, run_id: str, status: RunStatus) -> None:
    with runs.step(run_id) as writer:
        writer.set_status(status)


def test_start_on_unconfirmed_plant_is_refused(
    plants: PlantRepository,
    runs: RunRepository,
    ref: ReferenceSet,
    settings: RunSettings,
    upload: Upload,
) -> None:
    record_id = upload(confirm=False)
    with pytest.raises(SectionsNotConfirmed):
        _start(plants, runs, ref, settings, record_id)
    assert runs.records() == []


def test_start_on_unknown_plant_is_refused(
    plants: PlantRepository, runs: RunRepository, ref: ReferenceSet, settings: RunSettings
) -> None:
    with pytest.raises(PlantNotFound):
        _start(plants, runs, ref, settings, "plant:nothing:0")


def test_sample_mode_is_not_built_yet(
    plants: PlantRepository,
    runs: RunRepository,
    ref: ReferenceSet,
    settings: RunSettings,
    upload: Upload,
) -> None:
    """R21: Phase 2 accepts only mode full."""
    with pytest.raises(ModeNotBuilt):
        _start(plants, runs, ref, settings, upload(), mode="sample")


def test_start_stores_questions_equal_to_the_builder(
    plants: PlantRepository,
    runs: RunRepository,
    ref: ReferenceSet,
    settings: RunSettings,
    upload: Upload,
) -> None:
    record_id = upload()
    run = _start(plants, runs, ref, settings, record_id)
    assert (run.status, run.step, run.attempt) == (RunStatus.RUNNING, "analysis", 1)
    assert run.label.kind == RunLabelKind.LIVE
    stored = plants.get(record_id)
    assert stored is not None
    expected = build_questions(stored.record.plant_file, stored.sections, ref, run.id)
    assert runs.questions(run.id) == expected
    assert len(expected) == 98
    assert [s.id for s in runs.sections(run.id)] == run.section_snapshot
    assert len(run.section_snapshot) == 9
    events = runs.events(run.id)
    assert [(e.seq, e.type) for e in events] == [(1, EventType.RUN_STARTED)]
    assert events[0].payload == {"attempt": 1, "questions": 98, "sections": 9}


def test_run_id_matches_its_stored_inputs(
    plants: PlantRepository,
    runs: RunRepository,
    ref: ReferenceSet,
    settings: RunSettings,
    upload: Upload,
) -> None:
    run = _start(plants, runs, ref, settings, upload())
    stored = runs.get(run.id)
    assert stored is not None
    assert Run.model_validate(stored.model_dump()) == stored
    assert stored.reference_versions == dict(ref.versions)
    assert stored.routing_config == settings.routing_config
    assert stored.caps == settings.caps
    assert stored.prompt_versions == settings.prompt_versions


def test_identical_inputs_while_running_return_the_same_run(
    plants: PlantRepository,
    runs: RunRepository,
    ref: ReferenceSet,
    settings: RunSettings,
    upload: Upload,
) -> None:
    record_id = upload()
    first = _start(plants, runs, ref, settings, record_id)
    second = _start(plants, runs, ref, settings, record_id, cap=2.0)
    assert second.id == first.id
    assert len(runs.records()) == 1
    assert len(runs.questions(first.id)) == 98
    assert len(runs.events(first.id)) == 1


def test_changed_settings_give_a_different_run(
    plants: PlantRepository,
    runs: RunRepository,
    ref: ReferenceSet,
    settings: RunSettings,
    upload: Upload,
) -> None:
    record_id = upload()
    first = _start(plants, runs, ref, settings, record_id)
    other = replace(settings, prompt_versions={"orchestrator": "v2"})
    assert _start(plants, runs, ref, other, record_id).id != first.id


def test_after_cancel_a_new_start_is_attempt_2(
    plants: PlantRepository,
    runs: RunRepository,
    ref: ReferenceSet,
    settings: RunSettings,
    upload: Upload,
) -> None:
    record_id = upload()
    first = _start(plants, runs, ref, settings, record_id)
    _set_status(runs, first.id, RunStatus.CANCELLED)
    second = _start(plants, runs, ref, settings, record_id)
    assert second.id == f"{first.id}:2"
    assert second.attempt == 2
    assert len(runs.questions(second.id)) == 98
    assert runs.get(first.id) is not None


def test_stopped_cap_with_a_higher_cap_resumes_the_same_run(
    plants: PlantRepository,
    runs: RunRepository,
    ref: ReferenceSet,
    settings: RunSettings,
    upload: Upload,
) -> None:
    record_id = upload()
    first = _start(plants, runs, ref, settings, record_id, cap=1.0)
    _set_status(runs, first.id, RunStatus.STOPPED_CAP)
    resumed = _start(plants, runs, ref, settings, record_id, cap=1.5)
    assert resumed.id == first.id
    assert (resumed.status, resumed.spend_cap_usd) == (RunStatus.RUNNING, 1.5)


def test_stopped_cap_without_a_higher_cap_is_refused(
    plants: PlantRepository,
    runs: RunRepository,
    ref: ReferenceSet,
    settings: RunSettings,
    upload: Upload,
) -> None:
    record_id = upload()
    first = _start(plants, runs, ref, settings, record_id, cap=1.0)
    _set_status(runs, first.id, RunStatus.STOPPED_CAP)
    with pytest.raises(ids.CapReachedError):
        _start(plants, runs, ref, settings, record_id, cap=1.0)


def test_stopped_budget_resumes_the_same_run(
    plants: PlantRepository,
    runs: RunRepository,
    ref: ReferenceSet,
    settings: RunSettings,
    upload: Upload,
) -> None:
    record_id = upload()
    first = _start(plants, runs, ref, settings, record_id)
    _set_status(runs, first.id, RunStatus.STOPPED_BUDGET)
    resumed = _start(plants, runs, ref, settings, record_id)
    assert (resumed.id, resumed.status) == (first.id, RunStatus.RUNNING)


def test_run_keeps_its_section_records_after_a_re_propose(
    plants: PlantRepository,
    runs: RunRepository,
    ref: ReferenceSet,
    settings: RunSettings,
    upload: Upload,
) -> None:
    record_id = upload()
    run = _start(plants, runs, ref, settings, record_id)
    before = runs.sections(run.id)
    stored = plants.get(record_id)
    assert stored is not None
    renamed = [
        s.model_copy(update={"name": "renamed"})
        for s in rule_cut(stored.record.plant_file, record_id)
    ]
    plants.set_sections(record_id, renamed[:3], PlantStatus.SECTIONS_PROPOSED)
    assert runs.sections(run.id) == before
    assert all(s.name != "renamed" for s in runs.sections(run.id))
