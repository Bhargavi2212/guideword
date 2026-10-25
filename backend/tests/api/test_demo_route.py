"""GET /demo and the recorded store (deploy plan D2): the deployed site serves the recorded run from
its committed export, labelled recorded, with no key and nothing that can spend."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import export_recorded
import make_fixtures
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from guideword.api import models as api
from guideword.api.app import create_app
from guideword.schema.records import SpendEntry
from guideword.settings import Settings

NOW = datetime(2026, 10, 24, tzinfo=UTC)


@pytest.fixture(scope="module")
def export(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, Any]]:
    """The fixture generator's $0 fake run, exported as the site's recorded run."""
    work = tmp_path_factory.mktemp("demo")
    generator = make_fixtures.Generator(work)
    try:
        served = generator.build()
    finally:
        generator.client.close()
    ledger = [
        SpendEntry.model_validate_json(line)
        for line in (work / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    run_id = served["run_detail.json"]["run"]["id"]
    out = work / "recorded"
    export_recorded.export(work / "fixtures.db", run_id, out, ledger=ledger, secrets=[])
    return out, served


def _site(recorded: Path | None, **demo: str) -> TestClient:
    """The deployed app: hosted, no keys, reading the recorded export."""
    settings = Settings(
        _env_file=None,
        guideword_mock=False,
        guideword_env="hosted",
        nebius_api_key=SecretStr(""),
        tavily_api_key=SecretStr(""),
        internal_advance_secret=SecretStr(""),
        database_url="sqlite://",
        guideword_recorded_dir=None if recorded is None else str(recorded),
        **demo,
    )
    return TestClient(create_app(settings=settings, clock=lambda: NOW))


def _ids(served: dict[str, Any]) -> tuple[str, str]:
    shortlist = served["shortlist.json"]
    chain = next(i for i in shortlist["items"] if i["target_kind"] == "chain")
    return shortlist["run_id"], chain["target_id"]


def test_demo_returns_the_recorded_run_with_its_label_and_start_line(
    export: tuple[Path, dict[str, Any]],
) -> None:
    out, served = export
    run_id, target = _ids(served)
    site = _site(out, guideword_demo_run_id=run_id, guideword_demo_target_id=target)
    response = site.get("/demo")
    assert response.status_code == 200, response.text
    demo = api.DemoResponse.model_validate(response.json())
    assert demo.run.run.id == run_id and demo.shortlist.run_id == run_id
    assert demo.label.kind == "recorded" == demo.run.label.kind == demo.shortlist.label.kind
    assert demo.plant.plant_record_id == demo.run.run.plant_record_id
    assert [i.target_id for i in demo.shortlist.items] == [
        i["target_id"] for i in served["shortlist.json"]["items"]
    ]
    assert demo.start_target_id == target


def test_the_recorded_run_reads_through_every_run_route(
    export: tuple[Path, dict[str, Any]],
) -> None:
    out, served = export
    run_id, target = _ids(served)
    site = _site(out, guideword_demo_run_id=run_id)
    path = f"/runs/{quote(run_id, safe='')}"
    for rest in ("", "/shortlist", "/events", "/worksheet", "/coverage", "/sections"):
        assert site.get(path + rest).status_code == 200, rest
    assert site.get(f"{path}/records/{quote(target, safe='')}").status_code == 200


def test_demo_without_a_demo_run_is_501_naming_phase_7(
    export: tuple[Path, dict[str, Any]],
) -> None:
    out, _ = export
    response = _site(out).get("/demo")
    assert response.status_code == 501 and response.json()["phase"] == 7


def test_a_start_line_not_on_the_shortlist_is_never_served(
    export: tuple[Path, dict[str, Any]],
) -> None:
    out, served = export
    run_id, _ = _ids(served)
    site = _site(out, guideword_demo_run_id=run_id, guideword_demo_target_id="f:not:there")
    assert site.get("/demo").json().get("start_target_id") is None


def test_the_recorded_run_refuses_overrides_with_403(
    export: tuple[Path, dict[str, Any]],
) -> None:
    out, served = export
    run_id, target = _ids(served)
    response = _site(out, guideword_demo_run_id=run_id).post(
        f"/runs/{quote(run_id, safe='')}/overrides",
        json={"target_id": target, "action": "accept", "new_value": None, "reason": "r", "by": "B"},
    )
    assert response.status_code == 403


def test_a_keyless_hosted_site_refuses_every_route_that_could_spend(
    export: tuple[Path, dict[str, Any]],
) -> None:
    out, served = export
    run_id, _ = _ids(served)
    site = _site(out, guideword_demo_run_id=run_id)
    plant = served["plant_detail.json"]["plant_record_id"]
    start = site.post(
        "/runs",
        json={
            "plant_id": plant,
            "spend_cap_usd": 0.1,
            "mode": "full",
            "use": "development",
            "post_spend_cap_usd": 0.1,
        },
    )
    assert start.status_code == 409  # a laptop use: not this environment's
    assert site.post(f"/internal/runs/{quote(run_id, safe='')}/advance").status_code == 401
    proposal = site.post(f"/plants/{quote(plant, safe='')}/sections/propose")
    assert proposal.status_code == 200 and proposal.json()["suggestions"] == []
    assert site.get("/budget").json()["live_run_available"] is False


def test_the_run_itself_opens_in_the_drawer_with_its_stored_spend_and_label_note(
    export: tuple[Path, dict[str, Any]],
) -> None:
    """The header's spend is traced to the run (C12); the drawer shows the stored record, so a
    label's ledger cost and its stored spend can be read side by side (deploy plan §0.3)."""
    out, served = export
    run_id, _ = _ids(served)
    site = _site(out, guideword_demo_run_id=run_id)
    response = site.get(f"/runs/{quote(run_id, safe='')}/records/{quote(run_id, safe='')}")
    assert response.status_code == 200, response.text
    detail = api.RecordDetail.model_validate(response.json())
    assert detail.record_kind == "run"
    assert detail.record["spent_usd"] == served["run_detail.json"]["run"]["spent_usd"]
    assert detail.record["label"]["kind"] == "recorded"
    assert detail.parent_ids == [served["run_detail.json"]["run"]["plant_record_id"]]
