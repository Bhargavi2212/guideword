"""GET /demo and the recorded store (deploy plan D2): the deployed site serves the recorded run from
its committed export, labelled recorded, with no key and nothing that can spend."""

from collections.abc import Sequence
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


def _site(
    recorded: Path | Sequence[Path] | None, runs: Sequence[dict[str, Any]] | None = None
) -> TestClient:
    """The deployed app: hosted, no keys, reading the recorded exports."""
    dirs = [recorded] if isinstance(recorded, Path) else recorded
    settings = Settings(
        _env_file=None,
        guideword_mock=False,
        guideword_env="hosted",
        nebius_api_key=SecretStr(""),
        tavily_api_key=SecretStr(""),
        internal_advance_secret=SecretStr(""),
        database_url="sqlite://",
        guideword_recorded_dirs=None if dirs is None else [str(d) for d in dirs],
        guideword_demo_runs=None if runs is None else list(runs),
    )
    return TestClient(create_app(settings=settings, clock=lambda: NOW))


def _run(run_id: str, target: str | None = None, banner: str | None = None) -> dict[str, Any]:
    return {"run_id": run_id, "start_target_id": target, "banner": banner}


def _ids(served: dict[str, Any]) -> tuple[str, str]:
    shortlist = served["shortlist.json"]
    chain = next(i for i in shortlist["items"] if i["target_kind"] == "chain")
    return shortlist["run_id"], chain["target_id"]


def test_demo_returns_the_recorded_run_with_its_label_and_start_line(
    export: tuple[Path, dict[str, Any]],
) -> None:
    out, served = export
    run_id, target = _ids(served)
    site = _site(out, [_run(run_id, target)])
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
    site = _site(out, [_run(run_id)])
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
    site = _site(out, [_run(run_id, "f:not:there")])
    assert site.get("/demo").json().get("start_target_id") is None


def test_the_recorded_run_refuses_overrides_with_403(
    export: tuple[Path, dict[str, Any]],
) -> None:
    out, served = export
    run_id, target = _ids(served)
    response = _site(out, [_run(run_id)]).post(
        f"/runs/{quote(run_id, safe='')}/overrides",
        json={"target_id": target, "action": "accept", "new_value": None, "reason": "r", "by": "B"},
    )
    assert response.status_code == 403


def test_a_keyless_hosted_site_refuses_every_route_that_could_spend(
    export: tuple[Path, dict[str, Any]],
) -> None:
    out, served = export
    run_id, _ = _ids(served)
    site = _site(out, [_run(run_id)])
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
    site = _site(out, [_run(run_id)])
    response = site.get(f"/runs/{quote(run_id, safe='')}/records/{quote(run_id, safe='')}")
    assert response.status_code == 200, response.text
    detail = api.RecordDetail.model_validate(response.json())
    assert detail.record_kind == "run"
    assert detail.record["spent_usd"] == served["run_detail.json"]["run"]["spent_usd"]
    assert detail.record["label"]["kind"] == "recorded"
    assert detail.parent_ids == [served["run_detail.json"]["run"]["plant_record_id"]]


# --- contract v1.11: the site's runs, their banners and the picker (review plan R0) ------------


def test_a_banner_names_the_start_line_by_its_served_rank(
    export: tuple[Path, dict[str, Any]],
) -> None:
    out, served = export
    run_id, target = _ids(served)
    rank = next(i["rank"] for i in served["shortlist.json"]["items"] if i["target_id"] == target)
    site = _site(out, [_run(run_id, target, "Rebuilt from a report. Line #{start_rank} is it.")])
    demo = api.DemoResponse.model_validate(site.get("/demo").json())
    assert demo.runs[0].banner == f"Rebuilt from a report. Line #{rank} is it."
    assert demo.runs[0].start_target_id == target == demo.start_target_id


def test_a_banner_that_names_a_line_not_on_the_shortlist_is_left_out(
    export: tuple[Path, dict[str, Any]],
) -> None:
    out, served = export
    run_id, _ = _ids(served)
    site = _site(out, [_run(run_id, "f:not:there", "Line #{start_rank} is it.")])
    demo = api.DemoResponse.model_validate(site.get("/demo").json())
    assert demo.runs[0].banner is None and demo.runs[0].start_target_id is None
    plain = _site(out, [_run(run_id, None, "Rebuilt from a public report.")])
    assert plain.get("/demo").json()["runs"][0]["banner"] == "Rebuilt from a public report."


def test_several_exports_load_into_one_site_in_the_picker_order(
    export: tuple[Path, dict[str, Any]], tmp_path: Path
) -> None:
    out, served = export
    run_id, target = _ids(served)
    other = next(r["id"] for r in served["run_list.json"]["runs"] if r["id"] != run_id)
    second = tmp_path / "second"
    export_recorded.export(out.parent / "fixtures.db", other, second, ledger=[], secrets=[])
    site = _site([out, second], [_run(run_id, target, "first"), _run(other, None, "second")])
    demo = api.DemoResponse.model_validate(site.get("/demo").json())
    assert [r.run_id for r in demo.runs] == [run_id, other]
    assert demo.run.run.id == run_id and demo.start_target_id == target
    assert demo.runs[1].start_target_id is None and demo.runs[1].banner == "second"
    assert site.get(f"/runs/{quote(other, safe='')}").status_code == 200


def test_two_exports_that_disagree_on_a_shared_row_are_refused(
    export: tuple[Path, dict[str, Any]], tmp_path: Path
) -> None:
    import json

    from guideword.runs.recorded import load_recorded

    out, _ = export
    copy = tmp_path / "copy"
    copy.mkdir()
    for f in out.iterdir():
        (copy / f.name).write_bytes(f.read_bytes())
    plants = json.loads((copy / "plants.json").read_text(encoding="utf-8"))
    plants["rows"][0]["status"] = "draft" if plants["rows"][0]["status"] != "draft" else "x"
    (copy / "plants.json").write_text(json.dumps(plants), encoding="utf-8")
    load_recorded([out, out])  # the same row twice is one row
    with pytest.raises(ValueError, match="plants"):
        load_recorded([out, copy])
