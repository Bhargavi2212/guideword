"""Shared fixtures for the run store: a temp database with the §9 example confirmed."""

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from guideword.reference import ReferenceSet, load_reference_set
from guideword.runs.db import make_session_factory
from guideword.runs.plants import PlantRepository, load_plant, plant_facts
from guideword.runs.start import RunSettings
from guideword.runs.store import RunRepository
from guideword.sections.rules import rule_cut

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
T0 = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


def example() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    return data


@pytest.fixture(scope="session")
def ref() -> ReferenceSet:
    return load_reference_set()


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    return f"sqlite:///{(tmp_path / 'g.db').as_posix()}"


@pytest.fixture
def plants(db_url: str) -> PlantRepository:
    return PlantRepository(make_session_factory(db_url))


@pytest.fixture
def runs(db_url: str) -> RunRepository:
    return RunRepository(make_session_factory(db_url), Clock())


@pytest.fixture
def settings() -> RunSettings:
    return RunSettings(
        routing_config={"orchestrator": "ultra", "specialist_bulk": "lightning"},
        caps={"run_spend_cap_usd": 1.0, "orchestrator_max_steps": 60},
        prompt_versions={"orchestrator": "v1"},
    )


Upload = Callable[..., str]


@pytest.fixture
def upload(plants: PlantRepository, ref: ReferenceSet) -> Upload:
    """Store a plant; confirmed with its rule cut unless confirm=False."""

    def _upload(data: dict[str, Any] | None = None, *, confirm: bool = True) -> str:
        raw = data if data is not None else example()
        record, report = load_plant(raw, ref)
        assert record is not None, report.errors
        plants.add(record, raw, plant_facts(record.plant_file, record.id))
        if confirm:
            plants.confirm(record.id, rule_cut(record.plant_file, record.id))
        return record.id

    return _upload
