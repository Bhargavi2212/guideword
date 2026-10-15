"""Propose and confirm endpoints without mock mode (spec 1.3; plan P5, P7)."""

import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from guideword.api import models as api
from guideword.api.app import NOT_BUILT_PHASE, create_app
from guideword.runs.db import make_session_factory
from guideword.runs.plants import PlantRepository
from guideword.schema.plant import Plant
from guideword.sections.rules import rule_cut
from guideword.sections.suggest import FakeSuggester, Suggester
from guideword.settings import Settings

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
RULE_IDS = [
    "S-L-12",
    "S-L-12~P-1",
    "S-L-STM",
    "S-L-STM~TV-1",
    "S-MX-1",
    "S-P-1",
    "S-P-CHARGE",
    "S-TOTE-1",
    "S-W-1",
]


def _example() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    return data


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    return f"sqlite:///{(tmp_path / 'guideword.db').as_posix()}"


def _client(db_url: str, suggester: Suggester | None = None) -> TestClient:
    settings = Settings(_env_file=None, guideword_mock=False, database_url=db_url)
    return TestClient(create_app(settings=settings, suggester=suggester))


@pytest.fixture
def client(db_url: str) -> TestClient:
    return _client(db_url)


def _upload(client: TestClient) -> str:
    result = api.PlantUploadResult.model_validate(client.post("/plants", json=_example()).json())
    assert result.plant_record_id is not None
    return result.plant_record_id


def _url(record_id: str, tail: str = "") -> str:
    return f"/plants/{quote(record_id, safe='')}{tail}"


def _propose(client: TestClient, record_id: str) -> api.SectionProposal:
    response = client.post(_url(record_id, "/sections/propose"))
    assert response.status_code == 200, response.text
    return api.SectionProposal.model_validate(response.json())


def _put(client: TestClient, record_id: str, sections: list[Any]) -> Any:
    return client.put(
        _url(record_id, "/sections"),
        json={"sections": [s.model_dump(mode="json") for s in sections]},
    )


def _status(client: TestClient, record_id: str) -> str:
    return str(client.get(_url(record_id)).json()["status"])


def test_propose_and_put_are_built() -> None:
    """P7: no plant route is left in NOT_BUILT_PHASE."""
    assert not [route for route in NOT_BUILT_PHASE if route[1].startswith("/plants")]


def test_propose_returns_the_rule_cut_and_no_suggestions(client: TestClient) -> None:
    record_id = _upload(client)
    proposal = _propose(client, record_id)
    assert proposal.plant_record_id == record_id
    assert [s.id for s in proposal.sections] == RULE_IDS
    assert proposal.suggestions == []


def test_propose_then_put_moves_status_and_reads_back_identical(client: TestClient) -> None:
    record_id = _upload(client)
    assert _status(client, record_id) == "uploaded"
    proposal = _propose(client, record_id)
    assert _status(client, record_id) == "sections_proposed"
    detail = api.PlantDetail.model_validate(client.get(_url(record_id)).json())
    assert detail.sections == proposal.sections
    response = _put(client, record_id, proposal.sections)
    assert response.status_code == 200, response.text
    result = api.ConfirmSectionsResult.model_validate(response.json())
    assert (result.plant_record_id, result.status, result.section_ids) == (
        record_id,
        "sections_confirmed",
        RULE_IDS,
    )
    detail = api.PlantDetail.model_validate(client.get(_url(record_id)).json())
    assert detail.sections == proposal.sections
    assert detail.status == "sections_confirmed"


def test_propose_returns_only_valid_suggestions_and_stores_the_rule_cut(
    db_url: str, caplog: pytest.LogCaptureFixture
) -> None:
    good = api.SectionSuggestion(kind="purpose", section_ids=["S-MX-1"], purpose="Mix", reason="r")
    bad = api.SectionSuggestion(kind="merge", section_ids=["S-MX-1", "S-TOTE-1"], reason="r")
    client = _client(db_url, FakeSuggester([bad, good]))
    record_id = _upload(client)
    with caplog.at_level(logging.INFO, logger="guideword"):
        proposal = _propose(client, record_id)
    assert proposal.suggestions == [good]
    stored = api.PlantDetail.model_validate(client.get(_url(record_id)).json()).sections
    assert [s.id for s in stored] == RULE_IDS
    assert all(s.purpose is None for s in stored)
    rejected = [r for r in caplog.records if r.getMessage() == "section suggestion rejected"]
    assert len(rejected) == 1
    context = getattr(rejected[0], "context")  # noqa: B009
    assert context["plant_record_id"] == record_id
    assert context["suggestion"]["section_ids"] == ["S-MX-1", "S-TOTE-1"]
    assert "type" in context["reason"]


def test_repropose_after_confirm_clears_the_confirmed_set(db_url: str) -> None:
    client = _client(db_url)
    record_id = _upload(client)
    sections = _propose(client, record_id).sections
    assert _put(client, record_id, sections).status_code == 200
    _propose(client, record_id)
    assert _status(client, record_id) == "sections_proposed"
    stored = PlantRepository(make_session_factory(db_url)).get(record_id)
    assert stored is not None
    assert stored.record.confirmed_section_ids == []


def test_put_straight_after_upload_is_allowed_when_checks_pass(client: TestClient) -> None:
    record_id = _upload(client)
    sections = rule_cut(Plant.model_validate(_example()), record_id)
    assert _put(client, record_id, sections).status_code == 200
    assert _status(client, record_id) == "sections_confirmed"


def test_rename_keeps_the_id(client: TestClient) -> None:
    record_id = _upload(client)
    sections = _propose(client, record_id).sections
    renamed = [
        s.model_copy(update={"name": "Siloxane mixer"}) if s.id == "S-MX-1" else s for s in sections
    ]
    assert _put(client, record_id, renamed).status_code == 200
    stored = {
        s.id: s for s in api.PlantDetail.model_validate(client.get(_url(record_id)).json()).sections
    }
    assert stored["S-MX-1"].name == "Siloxane mixer"


def test_put_issues_are_409_one_per_line(client: TestClient) -> None:
    record_id = _upload(client)
    sections = [
        s for s in _propose(client, record_id).sections if s.id not in ("S-L-12", "S-P-CHARGE")
    ]
    response = _put(client, record_id, sections)
    assert response.status_code == 409
    lines = api.ErrorBody.model_validate(response.json()).detail.splitlines()
    assert [line.split(":")[0] for line in lines] == [
        "object_not_in_section P-CHARGE",
        "line_first_part_missing L-12",
    ]
    assert _status(client, record_id) == "sections_proposed"


def test_put_section_of_another_plant_is_409(client: TestClient) -> None:
    record_id = _upload(client)
    sections = _propose(client, record_id).sections
    moved = [s.model_copy(update={"plant_record_id": "plant:other:0"}) for s in sections[:1]]
    response = _put(client, record_id, [*moved, *sections[1:]])
    assert response.status_code == 409
    assert response.json()["detail"].startswith(f"section_of_other_plant {sections[0].id}:")


def test_propose_and_put_unknown_plant_is_404(client: TestClient) -> None:
    missing = "plant:nothing:0"
    assert client.post(_url(missing, "/sections/propose")).status_code == 404
    response = client.put(_url(missing, "/sections"), json={"sections": []})
    assert response.status_code == 404
    assert response.json()["detail"] == f"no plant {missing}"
