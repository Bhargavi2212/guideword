"""The plant endpoints without mock mode (spec 1.1, plan P3, P7, Q8)."""

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from guideword.api import models as api
from guideword.api.app import NOT_BUILT_PHASE, create_app
from guideword.settings import Settings

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
DEV_CASES = sorted((REPO / "cases" / "dev").glob("case_*.json"))
PLANT_ROUTES_BUILT_IN_PR_1 = {("GET", "/plants"), ("POST", "/plants"), ("GET", "/plants/{id}")}


def _example() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    return data


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "guideword.db"


@pytest.fixture
def client(db_path: Path) -> TestClient:
    settings = Settings(
        _env_file=None, guideword_mock=False, database_url=f"sqlite:///{db_path.as_posix()}"
    )
    return TestClient(create_app(settings=settings))


def _upload(client: TestClient, data: dict[str, Any]) -> api.PlantUploadResult:
    response = client.post("/plants", json=data)
    assert response.status_code == 200, response.text
    return api.PlantUploadResult.model_validate(response.json())


def _detail(client: TestClient, record_id: str) -> api.PlantDetail:
    response = client.get(f"/plants/{quote(record_id, safe='')}")
    assert response.status_code == 200, response.text
    return api.PlantDetail.model_validate(response.json())


def test_example_uploads_ok(client: TestClient) -> None:
    result = _upload(client, _example())
    assert result.ok
    assert result.errors == []
    assert result.plant_record_id is not None
    detail = _detail(client, result.plant_record_id)
    assert detail.status == "uploaded"
    facts = {f.id: f for f in detail.facts}
    assert facts["MX-1.design_pressure_kpa"].source == "assumed"
    assert "MX-1.operating.temperature.trip_high" in facts
    assert detail.sections == []


def test_upload_with_error_stores_nothing(client: TestClient) -> None:
    data = _example()
    data["equipment"][0]["location_id"] = "NOWHERE"
    result = _upload(client, data)
    assert not result.ok
    assert result.plant_record_id is None
    assert [(e.object_id, e.code) for e in result.errors] == [("TOTE-1", "bad_reference")]
    assert client.get("/plants").json() == {"plants": []}


def test_same_file_twice_returns_the_same_record_and_one_row(client: TestClient) -> None:
    first = _upload(client, _example())
    second = _upload(client, _example())
    assert first.plant_record_id == second.plant_record_id
    assert len(client.get("/plants").json()["plants"]) == 1


def test_changed_value_gives_a_new_record_id(client: TestClient) -> None:
    data = _example()
    first = _upload(client, data)
    data["equipment"][0]["volume_m3"] = 1.5
    second = _upload(client, data)
    assert first.plant_record_id != second.plant_record_id
    assert len(client.get("/plants").json()["plants"]) == 2


def test_not_stated_warnings_in_both_upload_and_detail(client: TestClient) -> None:
    result = _upload(client, _example())
    assert result.plant_record_id is not None
    detail = _detail(client, result.plant_record_id)
    for warnings in (result.warnings, detail.warnings):
        not_stated = [w for w in warnings if w.code == "source_not_stated"]
        p1 = [w for w in not_stated if w.object_id == "P-1"]
        assert any("P-1.type" in w.message for w in p1)
        assert len(not_stated) == sum(1 for f in detail.facts if f.source == "not stated")
    assert result.warnings == detail.warnings


def test_upload_warnings_include_validation_warnings_then_not_stated(client: TestClient) -> None:
    data = _example()
    del data["relief_devices"][0]["discharge"]
    result = _upload(client, data)
    codes = [w.code for w in result.warnings]
    first_not_stated = codes.index("source_not_stated")
    validation, not_stated = codes[:first_not_stated], codes[first_not_stated:]
    assert "relief_without_discharge" in validation
    assert "source_not_stated" not in validation
    assert set(not_stated) == {"source_not_stated"}
    assert result.plant_record_id is not None
    assert _detail(client, result.plant_record_id).warnings == result.warnings


def test_list_and_get_plant(client: TestClient) -> None:
    result = _upload(client, _example())
    listed = api.PlantList.model_validate(client.get("/plants").json())
    assert [(p.plant_record_id, p.plant_id, p.status) for p in listed.plants] == [
        (result.plant_record_id, "example_mixing_unit", "uploaded")
    ]


def test_url_encoded_record_id_is_found(client: TestClient) -> None:
    result = _upload(client, _example())
    assert result.plant_record_id is not None
    encoded = quote(result.plant_record_id, safe="")
    assert "%3A" in encoded
    assert client.get(f"/plants/{encoded}").status_code == 200


def test_unknown_plant_is_404(client: TestClient) -> None:
    response = client.get(f"/plants/{quote('plant:nothing:0', safe='')}")
    assert response.status_code == 404
    assert api.ErrorBody.model_validate(response.json()).detail == "no plant plant:nothing:0"


@pytest.mark.parametrize("path", DEV_CASES, ids=[p.stem for p in DEV_CASES])
def test_each_dev_case_uploads_with_no_errors(client: TestClient, path: Path) -> None:
    result = _upload(client, json.loads(path.read_text(encoding="utf-8")))
    assert result.ok, result.errors


def test_the_1_1_routes_are_built() -> None:
    """P7: the 1.1 routes left NOT_BUILT_PHASE in PR 1 (propose and PUT follow in PR 3)."""
    assert not PLANT_ROUTES_BUILT_IN_PR_1 & NOT_BUILT_PHASE.keys()


def test_no_database_is_created_until_a_plant_route_is_used(
    client: TestClient, db_path: Path
) -> None:
    # a route not built yet answers 501 without opening the store (runs are built in PR 10)
    assert client.get("/runs/run:x/shortlist").status_code == 501
    assert not db_path.exists()
    client.get("/plants")
    assert db_path.exists()
