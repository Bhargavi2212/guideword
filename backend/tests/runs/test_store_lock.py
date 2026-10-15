"""A step holds no database write lock while it runs (found building the orchestrator).

The cache commits each response on its own, from any thread, while a step is open; on SQLite
that only works if the step writes nothing until it commits.
"""

import threading
import time
from collections.abc import Callable

import pytest

from guideword.gateway.cache import ResponseCache
from guideword.gateway.transport import Reply
from guideword.reference import ReferenceSet
from guideword.runs.db import make_session_factory
from guideword.runs.plants import PlantRepository
from guideword.runs.start import RunSettings, start_run
from guideword.runs.store import RunRepository
from guideword.schema.enums import EventType, QuestionStatus

Upload = Callable[..., str]


def test_cache_commits_while_a_step_with_writes_is_open(
    plants: PlantRepository,
    runs: RunRepository,
    ref: ReferenceSet,
    settings: RunSettings,
    upload: Upload,
    db_url: str,
) -> None:
    run = start_run(
        plants, runs, ref, settings, plant_record_id=upload(), spend_cap_usd=1.0, mode="full"
    )
    cache = ResponseCache(make_session_factory(db_url))
    question = runs.questions(run.id)[0]
    with runs.step(run.id) as writer:
        writer.emit(EventType.STEP_STARTED, {"step": "analysis"})
        writer.put_question(question.model_copy(update={"status": QuestionStatus.ANSWERED}))
        started = time.perf_counter()
        errors: list[BaseException] = []

        def put() -> None:
            try:
                cache.put("k1", "m", "p/v1", Reply(content="{}", reasoning=None), 0.0)
            except BaseException as error:  # noqa: BLE001 - collected for the assert
                errors.append(error)

        thread = threading.Thread(target=put)
        thread.start()
        thread.join(10)
        assert errors == []
        assert time.perf_counter() - started < 2
    assert cache.get("k1") is not None
    assert runs.questions(run.id)[0].status == QuestionStatus.ANSWERED


def test_a_step_reads_its_own_pending_writes(
    plants: PlantRepository,
    runs: RunRepository,
    ref: ReferenceSet,
    settings: RunSettings,
    upload: Upload,
) -> None:
    run = start_run(
        plants, runs, ref, settings, plant_record_id=upload(), spend_cap_usd=1.0, mode="full"
    )
    first = runs.questions(run.id)[0]
    with runs.step(run.id) as writer:
        writer.put_question(first.model_copy(update={"status": QuestionStatus.ANSWERED}))
        assert writer.questions()[0].status == QuestionStatus.ANSWERED
        assert len(writer.questions()) == 98
    assert runs.questions(run.id)[0].status == QuestionStatus.ANSWERED


def test_a_failed_step_still_saves_nothing(
    plants: PlantRepository,
    runs: RunRepository,
    ref: ReferenceSet,
    settings: RunSettings,
    upload: Upload,
) -> None:
    run = start_run(
        plants, runs, ref, settings, plant_record_id=upload(), spend_cap_usd=1.0, mode="full"
    )
    first = runs.questions(run.id)[0]
    with pytest.raises(RuntimeError), runs.step(run.id) as writer:
        writer.put_question(first.model_copy(update={"status": QuestionStatus.ANSWERED}))
        writer.emit(EventType.STEP_STARTED, {"step": "analysis"})
        raise RuntimeError("killed")
    assert runs.questions(run.id)[0].status == QuestionStatus.OPEN
    assert len(runs.events(run.id)) == 1
