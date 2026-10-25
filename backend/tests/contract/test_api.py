"""The API contract and mock server (spec 0.8). TestClient only; no network."""

import io
import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

import export_openapi
import openpyxl
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from guideword.api import models as api
from guideword.api.app import NOT_BUILT_PHASE, create_app
from guideword.schema import ids
from guideword.schema.plant import Plant
from guideword.schema.records import Evidence
from guideword.settings import Settings
from guideword.tools.physics import heat_up_rate

FIXTURES = Path(__file__).resolve().parents[3] / "contract" / "fixtures"
SECRET = "advance-test-secret-123"
T0 = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
WORKSHEET_COLUMNS = [
    "Section",
    "Design intent",
    "Guideword",
    "Parameter",
    "Deviation",
    "Causes",
    "Consequences",
    "Existing safeguards",
    "Severity",
    "Likelihood",
    "Risk",
    "LOPA gap",
    "Recommendation",
    "Action owner",
    "Origin",
    "Evidence",
    "Status",
]

# PROJECT.md section 11 "API contract", in order.
CONTRACT_ROUTES = {
    ("GET", "/plants"),
    ("POST", "/plants"),
    ("GET", "/plants/{id}"),
    ("POST", "/plants/{id}/sections/propose"),
    ("PUT", "/plants/{id}/sections"),
    ("GET", "/runs"),
    ("POST", "/runs"),
    ("POST", "/runs/{id}/cancel"),
    ("GET", "/runs/{id}"),
    ("GET", "/runs/{id}/events"),
    ("GET", "/runs/{id}/sections"),
    ("GET", "/runs/{id}/questions"),
    ("POST", "/runs/{id}/questions"),
    ("GET", "/runs/{id}/shortlist"),
    ("GET", "/runs/{id}/worksheet"),
    ("GET", "/runs/{id}/coverage"),
    ("GET", "/runs/{id}/records/{record_id}"),
    ("POST", "/runs/{id}/overrides"),
    ("GET", "/runs/{id}/export.xlsx"),
    ("GET", "/runs/{id}/export/coverage.json"),
    ("GET", "/runs/{id}/export/run.json"),
    ("GET", "/demo"),
    ("GET", "/budget"),
    ("POST", "/internal/runs/{id}/advance"),
}


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


def _settings(mock: bool = True, secret: str = SECRET) -> Settings:
    return Settings(
        _env_file=None,
        guideword_mock=mock,
        internal_advance_secret=SecretStr(secret),
        global_budget_usd=25.0,
    )


def _client(
    mock: bool = True, secret: str = SECRET, clock: Clock | None = None, fixtures: Path = FIXTURES
) -> TestClient:
    return TestClient(
        create_app(settings=_settings(mock, secret), clock=clock or Clock(), fixtures_dir=fixtures)
    )


def _fixture(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return data


# the main generated run (the run list also holds its cancelled and failed attempts)
RUN = _fixture("run_detail.json")["run"]["id"]
PLANT = _fixture("plant_list.json")["plants"][0]["plant_record_id"]
R = quote(RUN, safe="")
P = quote(PLANT, safe="")


def _path(template: str) -> str:
    record = quote(_fixture("record_detail.json")["record_id"], safe="")
    return template.replace("{record_id}", record).replace(
        "{id}", R if template.startswith(("/runs", "/internal")) else P
    )


# --- the contract -------------------------------------------------------------------------------


def test_routes_are_exactly_the_section_11_endpoints() -> None:
    app = create_app(settings=_settings(), clock=Clock(), fixtures_dir=FIXTURES)
    routes = {
        (method, route.path)
        for route in app.routes
        for method in getattr(route, "methods", set())
        if method not in ("HEAD", "OPTIONS")
        and not route.path.startswith(("/openapi", "/docs", "/redoc"))
    }
    assert routes == CONTRACT_ROUTES


@pytest.mark.parametrize("model, name", list(api.RESPONSE_FIXTURES.items()), ids=lambda x: str(x))
def test_every_response_model_has_a_valid_fixture(model: type[Any], name: str) -> None:
    model.model_validate(_fixture(name))


def test_fixtures_describe_mock_plant_a_only() -> None:
    plant = _fixture("mock_plant_a.json")
    assert plant["plant_id"] == "mock_plant_a"
    for path in FIXTURES.glob("*.json"):
        text = path.read_text(encoding="utf-8").lower()
        for word in ("csb", "geismar", "williams", "port neches", "didion", "husky"):
            assert word not in text, f"{path.name} mentions {word}"


def _walk(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [value, *(d for v in value.values() for d in _walk(v))]
    if isinstance(value, list):
        return [d for v in value for d in _walk(v)]
    return []


# R45 by step (Bhargavi, 2026-10-24): the post-analysis steps, fixed here and not read from the
# code. Their calls count against the post cap only (Bhargavi, 2026-10-20).
POST_STEPS = ("chains", "chain_severity", "lopa", "recommendations", "evidence")


def test_fixture_run_spend_matches_its_calls_by_step() -> None:
    """R45: each `model_call` event belongs to the step it was written in (the last
    `step_started` before it), so a refused call's attempt records count under their step.
    `cap_spent_usd` is the analysis calls' `cap_cost_usd`; `post_spent_usd` is the
    post-analysis calls' `cost_usd`; `spent_usd == cap_spent_usd + post_spent_usd`; and a
    paid call counts what it cost."""
    dump = _fixture("run_dump.json")
    run = dump["run"]
    step: str | None = None
    analysis_cap = post_spent = 0.0
    calls = post_calls = 0
    for event in dump["events"]:
        if event["type"] == "step_started":
            step = event["payload"]["step"]
        elif event["type"] == "model_call":
            payload = event["payload"]
            calls += 1
            if step in POST_STEPS:
                post_calls += 1
                post_spent += payload["cost_usd"]
            else:
                analysis_cap += payload["cap_cost_usd"]
            if not payload["cache_hit"]:
                assert payload["cap_cost_usd"] == payload["cost_usd"]
    assert calls and post_calls and post_spent > 0
    assert run["cap_spent_usd"] == pytest.approx(analysis_cap, rel=1e-12)
    assert run["spent_usd"] == pytest.approx(run["cap_spent_usd"] + post_spent, rel=1e-12)
    # every fixture that shows this run shows the same two figures
    for path in FIXTURES.glob("*.json"):
        for obj in _walk(json.loads(path.read_text(encoding="utf-8"))):
            if obj.get("id") == run["id"] and "spent_usd" in obj:
                assert (obj["spent_usd"], obj["cap_spent_usd"]) == (
                    run["spent_usd"],
                    run["cap_spent_usd"],
                ), path.name


def test_openapi_json_matches_the_app() -> None:
    committed = (Path(export_openapi.OUT)).read_text(encoding="utf-8")
    assert committed == export_openapi.render(), "run: python scripts/export_openapi.py"


# --- mock responses -------------------------------------------------------------------------------

RUN_GETS = [
    "/runs/{id}",
    "/runs/{id}/events",
    "/runs/{id}/sections",
    "/runs/{id}/questions",
    "/runs/{id}/shortlist",
    "/runs/{id}/worksheet",
    "/runs/{id}/coverage",
    "/runs/{id}/records/{record_id}",
    "/runs/{id}/export/coverage.json",
    "/runs/{id}/export/run.json",
    "/demo",
]


@pytest.mark.parametrize("template", RUN_GETS)
def test_run_related_responses_carry_a_mock_label(template: str) -> None:
    response = _client().get(_path(template))
    assert response.status_code == 200, response.text
    assert response.json()["label"]["kind"] == "mock"


def test_run_list_runs_are_labelled_mock() -> None:
    runs = _client().get("/runs").json()["runs"]
    assert runs and all(run["label"]["kind"] == "mock" for run in runs)


@pytest.mark.parametrize(
    "method, template, body",
    [
        ("GET", "/plants", None),
        ("POST", "/plants", {"plant_id": "x", "schema_version": "1.0"}),
        ("GET", "/plants/{id}", None),
        ("POST", "/plants/{id}/sections/propose", None),
        ("PUT", "/plants/{id}/sections", {"sections": []}),
        (
            "POST",
            "/runs",
            {
                "plant_id": PLANT,
                "spend_cap_usd": 1.0,
                "mode": "full",
                "use": "development",
                "post_spend_cap_usd": 0.3,
            },
        ),
        ("POST", "/runs/{id}/cancel", None),
        ("GET", "/budget", None),
    ],
)
def test_other_mock_endpoints_answer(method: str, template: str, body: Any) -> None:
    response = _client().request(method, _path(template), json=body)
    assert response.status_code == 200, response.text


def test_unknown_run_is_404() -> None:
    response = _client().get("/runs/" + quote("run:0000000000000000", safe=""))
    assert response.status_code == 404


def test_question_filters() -> None:
    client = _client()
    answered = client.get(_path("/runs/{id}/questions"), params={"status": "answered"}).json()
    assert answered["questions"] and all(q["status"] == "answered" for q in answered["questions"])
    pairs = client.get(_path("/runs/{id}/questions"), params={"kind": "chemical_pair"}).json()
    assert [q["kind"] for q in pairs["questions"]] == ["chemical_pair"]


def test_engineer_question_is_created_open_with_an_eng_id() -> None:
    text = "What if the hose is left on the tote?"
    response = _client().post(
        _path("/runs/{id}/questions"), json={"section_id": "S-L-12", "text": text}
    )
    assert response.status_code == 200, response.text
    question = response.json()["question"]
    assert question["id"] == ids.engineer_question_id("S-L-12", text)
    assert (question["origin"], question["kind"], question["status"]) == (
        "engineer",
        "engineer",
        "open",
    )
    assert response.json()["label"]["kind"] == "mock"


def test_engineer_question_needs_a_section_of_the_run() -> None:
    response = _client().post(
        _path("/runs/{id}/questions"), json={"section_id": "S-NOPE", "text": "x"}
    )
    assert response.status_code == 404


def test_mock_override_is_echoed_not_stored() -> None:
    body = {
        "target_id": "q",
        "action": "answer",
        "new_value": {"text": "No: the hose is removed."},
        "reason": "Engineer's answer",
        "by": "Reviewer",
    }
    response = _client().post(_path("/runs/{id}/overrides"), json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["stored"] is False
    assert result["override"]["action"] == "answer"
    value = {"text": "No: the hose is removed."}
    assert result["override"]["id"] == ids.override_id("q", "answer", value)


def test_worksheet_export_is_a_workbook_with_the_section_5_columns() -> None:
    response = _client().get(_path("/runs/{id}/export.xlsx"))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    sheet = openpyxl.load_workbook(io.BytesIO(response.content)).active
    assert sheet is not None
    rows = list(sheet.iter_rows(values_only=True))
    assert list(rows[0]) == WORKSHEET_COLUMNS
    assert len(rows) - 1 == len(_fixture("worksheet.json")["rows"])


# --- events over injected time -------------------------------------------------------------------


def test_events_are_released_over_about_20_seconds() -> None:
    clock = Clock()
    client = _client(clock=clock)
    total = len(_fixture("events_page.json")["events"])
    first = client.get(_path("/runs/{id}/events")).json()
    assert len(first["events"]) == 1
    clock.now = T0 + timedelta(seconds=10)
    middle = client.get(_path("/runs/{id}/events"), params={"after": first["next_after"]}).json()
    assert 0 < len(middle["events"]) < total - 1
    assert middle["events"][0]["seq"] == first["next_after"] + 1
    clock.now = T0 + timedelta(seconds=20)
    rest = client.get(_path("/runs/{id}/events"), params={"after": middle["next_after"]}).json()
    assert rest["next_after"] == total
    seen = len(first["events"]) + len(middle["events"]) + len(rest["events"])
    assert seen == total


def test_events_after_the_last_seq_are_empty() -> None:
    clock = Clock()
    client = _client(clock=clock)
    client.get(_path("/runs/{id}/events"))
    clock.now = T0 + timedelta(seconds=60)
    total = len(_fixture("events_page.json")["events"])
    page = client.get(_path("/runs/{id}/events"), params={"after": total}).json()
    assert page["events"] == []
    assert page["next_after"] == total


# --- advance, 403, 409, 501 ---------------------------------------------------------------------


def test_advance_without_the_secret_is_401() -> None:
    assert _client().post(_path("/internal/runs/{id}/advance")).status_code == 401


def test_advance_with_a_wrong_secret_is_401() -> None:
    response = _client().post(
        _path("/internal/runs/{id}/advance"), headers={"X-Internal-Secret": "no"}
    )
    assert response.status_code == 401


def test_advance_with_the_secret_in_mock_mode_is_202() -> None:
    response = _client().post(
        _path("/internal/runs/{id}/advance"), headers={"X-Internal-Secret": SECRET}
    )
    assert response.status_code == 202
    assert response.json() == {"accepted": True}


def test_an_empty_secret_never_matches() -> None:
    response = _client(secret="").post(
        _path("/internal/runs/{id}/advance"), headers={"X-Internal-Secret": ""}
    )
    assert response.status_code == 401


@pytest.fixture
def extra_fixtures(tmp_path: Path) -> Path:
    """A fixture copy with test-only records: a recorded run, a stopped_cap run, an
    unconfirmed plant. contract/fixtures/ itself stays mock-only."""
    target = tmp_path / "fixtures"
    shutil.copytree(FIXTURES, target)
    runs = json.loads((target / "run_list.json").read_text(encoding="utf-8"))
    base = runs["runs"][0]
    recorded = {
        **base,
        "label": {"kind": "recorded", "recorded_at": "2026-10-20T10:00:00Z", "cost_usd": 0.4},
    }
    recorded["attempt"] = 2
    recorded["id"] = f"{base['id']}:2"
    capped = {**base, "status": "stopped_cap", "attempt": 3, "id": f"{base['id']}:3"}
    runs["runs"] += [recorded, capped]
    (target / "run_list.json").write_text(json.dumps(runs), encoding="utf-8")
    plants = json.loads((target / "plant_list.json").read_text(encoding="utf-8"))
    plants["plants"].append(
        {
            "plant_record_id": "plant:unconfirmed_plant:0000000000000000",
            "plant_id": "unconfirmed_plant",
            "status": "uploaded",
        }
    )
    (target / "plant_list.json").write_text(json.dumps(plants), encoding="utf-8")
    return target


def test_override_on_a_recorded_run_is_403(extra_fixtures: Path) -> None:
    body = {"target_id": "q", "action": "accept", "new_value": None, "reason": "r", "by": "Judge"}
    path = "/runs/" + quote(f"{RUN}:2", safe="") + "/overrides"
    response = _client(fixtures=extra_fixtures).post(path, json=body)
    assert response.status_code == 403
    assert response.json()["detail"] == "recorded run is read-only"


def test_start_run_on_an_unconfirmed_plant_is_409(extra_fixtures: Path) -> None:
    body = {
        "plant_id": "plant:unconfirmed_plant:0000000000000000",
        "spend_cap_usd": 1.0,
        "mode": "full",
        "use": "development",
        "post_spend_cap_usd": 0.3,
    }
    response = _client(fixtures=extra_fixtures).post("/runs", json=body)
    assert response.status_code == 409
    assert response.json()["detail"] == "sections not confirmed"


# the stopped_cap copy keeps the generated run's own cap
STORED_CAP = _fixture("run_detail.json")["run"]["spend_cap_usd"]


@pytest.mark.parametrize("cap", [STORED_CAP, STORED_CAP / 2])
def test_restart_of_a_stopped_cap_run_without_a_higher_cap_is_409(
    extra_fixtures: Path, cap: float
) -> None:
    body = {
        "plant_id": PLANT,
        "spend_cap_usd": cap,
        "mode": "full",
        "use": "development",
        "post_spend_cap_usd": 0.3,
    }
    response = _client(fixtures=extra_fixtures).post("/runs", json=body)
    assert response.status_code == 409
    assert response.json()["detail"] == "cap reached; raise spend_cap_usd to continue"


def test_restart_of_a_stopped_cap_run_with_a_higher_cap_starts(extra_fixtures: Path) -> None:
    body = {
        "plant_id": PLANT,
        "spend_cap_usd": 1.5,
        "mode": "full",
        "use": "development",
        "post_spend_cap_usd": 0.3,
    }
    assert _client(fixtures=extra_fixtures).post("/runs", json=body).status_code == 200


# Routes leave NOT_BUILT_PHASE as their phase builds them (Phase 1 plan, P7).
UNBUILT_ROUTES = sorted(
    route
    for route in CONTRACT_ROUTES - {("POST", "/internal/runs/{id}/advance")}
    if route in NOT_BUILT_PHASE
)


def test_not_built_phase_names_only_contract_routes() -> None:
    assert NOT_BUILT_PHASE.keys() <= CONTRACT_ROUTES


@pytest.mark.parametrize("method, template", UNBUILT_ROUTES)
def test_without_mock_mode_every_unbuilt_route_is_501_naming_its_phase(
    method: str, template: str
) -> None:
    bodies: dict[str, Any] = {
        "/plants": {"plant_id": "x", "schema_version": "1.0"},
        "/runs": {
            "plant_id": PLANT,
            "spend_cap_usd": 1.0,
            "mode": "full",
            "use": "development",
            "post_spend_cap_usd": 0.3,
        },
        "/plants/{id}/sections": {"sections": []},
        "/runs/{id}/questions": {"section_id": "S-L-12", "text": "x"},
        "/runs/{id}/overrides": {
            "target_id": "q",
            "action": "accept",
            "new_value": None,
            "reason": "r",
            "by": "b",
        },
    }
    body = bodies.get(template) if method in ("POST", "PUT") else None
    response = _client(mock=False).request(method, _path(template), json=body)
    assert response.status_code == 501, (method, template, response.text)
    detail = response.json()
    assert detail["phase"] == NOT_BUILT_PHASE[(method, template)]
    assert f"phase {detail['phase']}" in detail["detail"]


def test_advance_without_mock_mode_checks_the_secret_before_the_run(tmp_path: Path) -> None:
    """Built in PR 10 (spec 2.8): the secret first, then the run; a temporary store, never
    the repo's guideword.db."""
    settings = _settings(mock=False).model_copy(
        update={"database_url": f"sqlite:///{(tmp_path / 'g.db').as_posix()}"}
    )
    client = TestClient(create_app(settings=settings, clock=Clock()))
    assert client.post(_path("/internal/runs/{id}/advance")).status_code == 401
    response = client.post(
        _path("/internal/runs/{id}/advance"), headers={"X-Internal-Secret": SECRET}
    )
    assert response.status_code == 404


# --- contract v1.2: hypotheses and tiers (R50) --------------------------------------------------


def test_shortlist_item_new_fields_default_for_older_items() -> None:
    old = dict(_fixture("shortlist.json")["items"][0])
    for key in ("tier", "hypothesis_id", "hypothesis_rank", "hypothesis", "support_finding_ids"):
        old.pop(key, None)
    item = api.ShortlistItem.model_validate(old)
    assert item.tier == "also_found"
    assert (item.hypothesis_id, item.hypothesis_rank, item.hypothesis) == (None, None, None)
    assert item.support_finding_ids == []


def test_a_hypothesis_item_carries_its_hypothesis() -> None:
    item = next(i for i in _fixture("shortlist.json")["items"] if i["target_kind"] == "hypothesis")
    bad = {**item, "hypothesis": None}
    with pytest.raises(ValueError, match="hypothesis"):
        api.ShortlistItem.model_validate(bad)


def test_fixture_shortlist_shows_each_tier_and_a_hypothesis_item() -> None:
    items = api.Shortlist.model_validate(_fixture("shortlist.json")).items
    assert {i.tier for i in items} == {"confirmed", "also_found", "unconfirmed"}
    confirmed = next(i for i in items if i.tier == "confirmed")
    assert confirmed.hypothesis is not None and confirmed.support_finding_ids
    assert confirmed.hypothesis_id == confirmed.hypothesis.id
    assert confirmed.hypothesis_rank == confirmed.hypothesis.rank
    assert any(i.target_kind == "hypothesis" for i in items)


def test_mock_serves_the_hypothesis_record_too() -> None:
    hypothesis = _fixture("record_detail_hypothesis.json")
    assert hypothesis["record_kind"] == "hypothesis" and hypothesis["record_id"].startswith("h:")
    client = _client()
    path = f"/runs/{quote(RUN, safe='')}/records/{quote(hypothesis['record_id'], safe='')}"
    response = client.get(path)
    assert response.status_code == 200
    assert response.json()["record"]["id"] == hypothesis["record_id"]
    finding = _fixture("record_detail.json")["record_id"]
    assert (
        client.get(f"/runs/{quote(RUN, safe='')}/records/{quote(finding, safe='')}").status_code
        == 200
    )


def test_run_dump_carries_hypotheses() -> None:
    dump = api.RunDump.model_validate(_fixture("run_dump.json"))
    assert dump.hypotheses and all(h.run_id == dump.run.id for h in dump.hypotheses)


def test_mock_events_include_both_hypothesis_events() -> None:
    types = {e["type"] for e in _fixture("events_page.json")["events"]}
    assert {"hypothesis_added", "hypothesis_dropped"} <= types


# --- contract v1.3: rejected section suggestions (R23) ------------------------------------------


def test_section_proposal_without_rejected_still_validates() -> None:
    """Additive: a proposal from an older server, with no `rejected`, is valid and has none."""
    old = dict(_fixture("section_proposal.json"))
    old.pop("rejected", None)
    assert api.SectionProposal.model_validate(old).rejected == []


def test_a_rejected_suggestion_carries_the_suggestion_and_the_reason() -> None:
    proposal = api.SectionProposal.model_validate(
        _fixture("section_proposal.json")
        | {
            "rejected": [
                {
                    "suggestion": {
                        "kind": "merge",
                        "section_ids": ["S-NOPE"],
                        "purpose": None,
                        "reason": "one tank",
                    },
                    "reason": "unknown section S-NOPE",
                }
            ]
        }
    )
    [rejected] = proposal.rejected
    assert rejected.suggestion.section_ids == ["S-NOPE"]
    assert rejected.reason == "unknown section S-NOPE"


def test_the_mock_proposal_lists_no_rejections() -> None:
    assert _fixture("section_proposal.json")["rejected"] == []


# --- contract v1.4: post-analysis records and override values (spec 3.8, plan PR 1) -------------


def _override(action: str, new_value: Any, target: str = "f:x") -> api.OverrideRequest:
    return api.OverrideRequest.model_validate(
        {"target_id": target, "action": action, "new_value": new_value, "reason": "r", "by": "B"}
    )


@pytest.mark.parametrize(
    ("action", "new_value"),
    [
        ("accept", None),
        ("reject", None),
        ("edit", {"action": "Add an independent high-temperature trip"}),
        ("edit", {"consequence": "the batch overheats"}),
        ("edit", {"purpose": "Mix the batch"}),
        ("change_credit", {"layer_id": "PSV-1", "credited": True}),
        ("change_severity", {"severity_class": "S4"}),
        ("answer", {"text": "Checked with operations: not credible here"}),
    ],
)
def test_override_values_of_each_action_validate(action: str, new_value: Any) -> None:
    assert _override(action, new_value).action == action


@pytest.mark.parametrize(
    ("action", "new_value"),
    [
        ("accept", {"anything": 1}),
        ("reject", "no"),
        ("edit", {"severity_class": "S5"}),  # only action, consequence or purpose
        ("edit", {"action": "a", "consequence": "b"}),  # one field per edit
        ("edit", {"action": ""}),
        ("change_credit", {"layer_id": "PSV-1"}),
        ("change_credit", {"layer_id": "PSV-1", "credited": "yes", "pfd": 0.01}),
        ("change_severity", {"severity_class": "S9"}),
        ("answer", {}),
        ("answer", {"text": ""}),
    ],
)
def test_bad_override_values_are_refused(action: str, new_value: Any) -> None:
    with pytest.raises(ValidationError):
        _override(action, new_value)


def _v14() -> tuple[api.Shortlist, api.RunDump]:
    return (
        api.Shortlist.model_validate(_fixture("shortlist.json")),
        api.RunDump.model_validate(_fixture("run_dump.json")),
    )


def test_v14_fixtures_show_each_post_analysis_record_kind() -> None:
    """A rated chain, a complete and an incomplete LOPA record, a "not argued — no credit"
    layer, an argued layer and a recommendation."""
    shortlist, dump = _v14()
    chain = next(i.chain for i in shortlist.items if i.chain is not None)
    assert chain.severity_class is not None and chain.severity_reason
    records = dump.lopa_records
    assert any(r.complete for r in records) and any(not r.complete for r in records)
    incomplete = next(r for r in records if not r.complete)
    assert incomplete.missing_fact_ids and incomplete.gap is None
    layers = [layer for r in records for layer in r.layers]
    assert any(layer.reason == "not argued — no credit" for layer in layers)
    assert any(layer.applies is not None and layer.argument for layer in layers)
    assert dump.recommendations


def test_v14_fixtures_apply_no_modifier_and_list_every_kind_not_applied() -> None:
    """P3-3: no conditional modifier in Phase 3; each record lists the four kinds."""
    _, dump = _v14()
    kinds = {"ignition_probability", "explosion_given_ignition", "vulnerability", "time_at_risk"}
    for record in dump.lopa_records:
        assert record.modifiers == []
        assert {m.kind for m in record.modifiers_not_applied} == kinds
        assert all(m.reason == "no plant fact or rule" for m in record.modifiers_not_applied)


def test_shortlist_item_lopa_carries_severity_and_every_layer() -> None:
    """Spec 3.8: the item's LOPA has its severity and the full layer list (a record with no
    candidate layer, like the chain's, has an empty one)."""
    shortlist, dump = _v14()
    by_id = {r.id: r for r in dump.lopa_records}
    lopas = [item.lopa for item in shortlist.items if item.lopa is not None]
    assert lopas and all(lopa.severity_class is not None for lopa in lopas)
    assert all(lopa.layers == by_id[lopa.id].layers for lopa in lopas)
    assert any(lopa.layers for lopa in lopas)


def test_shortlist_lopa_records_match_the_run_dump() -> None:
    shortlist, dump = _v14()
    by_id = {r.id: r for r in dump.lopa_records}
    for item in shortlist.items:
        if item.lopa is not None:
            assert by_id[item.lopa.id] == item.lopa


def test_the_mock_override_result_uses_the_v14_change_severity_shape() -> None:
    override = api.OverrideResult.model_validate(_fixture("override_result.json")).override
    assert api.ChangeSeverityValue.model_validate(override.new_value).severity_class == "S4"
    assert override.id == ids.override_id(override.target_id, override.action, override.new_value)


# --- contract v1.5: shortlist card flags (Bhargavi, 2026-10-20) ---------------------------------


def test_shortlist_item_flags_default_to_empty_for_older_items() -> None:
    old = dict(_fixture("shortlist.json")["items"][0])
    old.pop("flags", None)
    assert api.ShortlistItem.model_validate(old).flags == []


SKIPPED_BLOCKED_IN = (
    "evidence skipped: missing L-STM.operating.temperature.normal, "
    "SIH.vapor_pressure_points, KOH.vapor_pressure_points"
)


def _cards() -> dict[str, api.ShortlistItem]:
    """The generated shortlist's six cards, by which line they are."""
    items = api.Shortlist.model_validate(_fixture("shortlist.json")).items
    prefixes = {
        "pair": "f:pair:KOH:SIH:",
        "chain": "ch:",
        "mx1": "f:m:S-MX-1:more:temperature:",
        "relief": "f:relief:PSV-1:",
        "l12": "f:m:S-L-12:reverse:flow:",
        "hypothesis": "h:",
    }
    cards = {}
    for name, prefix in prefixes.items():
        [card] = [i for i in items if i.target_id.startswith(prefix)]
        cards[name] = card
    assert len(items) == len(cards)
    return cards


def test_fixture_shortlist_pins_each_cards_flags() -> None:
    """Each card's flags, written by hand (Bhargavi, 2026-10-24)."""
    flags = {name: card.flags for name, card in _cards().items()}
    assert flags == {
        "pair": [],
        "chain": [SKIPPED_BLOCKED_IN],
        "mx1": [SKIPPED_BLOCKED_IN],
        "relief": [SKIPPED_BLOCKED_IN],
        "l12": ["incomplete LOPA: gap unknown"],
        "hypothesis": [
            "not confirmed by the checks — engineer to review",
            "no LOPA: unconfirmed: no finding to analyse",
        ],
    }
    items = api.Shortlist.model_validate(_fixture("shortlist.json")).items
    demo = api.DemoResponse.model_validate(_fixture("demo_response.json"))
    assert demo.shortlist.items == items


# --- contract v1.6: the gap as the engineer reads it (Bhargavi, 2026-10-20) --------------------


def test_shortlist_item_gap_text_defaults_to_none_for_older_items() -> None:
    old = dict(_fixture("shortlist.json")["items"][0])
    old.pop("gap_text", None)
    assert api.ShortlistItem.model_validate(old).gap_text is None


def test_fixture_shortlist_pins_the_gap_text_on_every_line_with_lopa() -> None:
    """One text per line, written by the backend; the card shows it and formats no number.
    The expected strings are written by hand from the formatter rule: the gap to the nearest
    order of magnitude, then mitigated and tolerable as "1 in N years". The two gaps with
    float noise (0.1 x 0.1 / 0.001, and the chain's 0.01 / 1e-4) display as clean numbers."""
    cards = _cards()
    gaps = {name: (card.gap, card.gap_text) for name, card in cards.items()}
    assert gaps == {
        "pair": (
            1000.0,
            "about 1,000× tolerable — mitigated about 1 in 10 years, "
            "tolerable about 1 in 10,000 years",
        ),
        "relief": (
            10.0,
            "about 10× tolerable — mitigated about 1 in 1,000 years, "
            "tolerable about 1 in 10,000 years",
        ),
        "chain": (
            100.00000000000001,
            "about 100× tolerable — mitigated about 1 in 100 years, "
            "tolerable about 1 in 10,000 years",
        ),
        "mx1": (
            10.000000000000002,
            "about 10× tolerable — mitigated about 1 in 100 years, "
            "tolerable about 1 in 1,000 years",
        ),
        "l12": (None, "incomplete: L-12.length_m missing"),
        "hypothesis": (None, None),
    }
    items = api.Shortlist.model_validate(_fixture("shortlist.json")).items
    demo = api.DemoResponse.model_validate(_fixture("demo_response.json"))
    assert demo.shortlist.items == items


def test_mock_heat_up_time_is_the_hand_worked_value() -> None:
    """MX-1 in mock_plant_a.json (fictional values, Bhargavi, 2026-10-24):
    rate = duty x 60 / (volume x lowest density x lowest heat capacity)
         = 500 kW x 60 / (10 m3 x 1000 kg/m3 x 1.5 kJ/kg/K)   (SIH: 1000 < 1450, 1.5 < 3.0)
         = 30000 / 15000 = 2.0 degC/min;
    minutes = (design_max 80 - normal 25) / 2.0 = 27.5, under the 60-minute confirm line."""
    plant = Plant.model_validate(_fixture("mock_plant_a.json"))
    assert heat_up_rate("MX-1", plant, 60.0).value == pytest.approx(27.5, rel=1e-9)
    [evidence] = [e for e in _mock_evidence() if e["id"].endswith(":calculation:heat_up_rate-MX-1")]
    assert evidence["verdict"] == "confirmed"
    assert "MX-1.heat_duty_kw" in evidence["fact_ids"]


# --- contract v1.7: superseded post-analysis records (Bhargavi, 2026-10-21) ---------------------


def test_run_dump_superseded_defaults_to_empty_for_older_dumps() -> None:
    old = dict(_fixture("run_dump.json"))
    old.pop("superseded", None)
    assert api.RunDump.model_validate(old).superseded == []
    assert api.RunDump.model_validate(_fixture("run_dump.json")).superseded == []


def test_a_superseded_record_is_kept_verbatim_with_its_kind_and_passes() -> None:
    """A re-run from `chains` copies each old chain, LOPA record, recommendation and post-step
    model call here, never changed; `pass_seq` is the `run_extended` event that began its
    pass and `superseded_seq` the one that replaced it."""
    dump = _fixture("run_dump.json")
    chain = dump["chains"][0]
    item = api.SupersededRecord(kind="chain", pass_seq=3, superseded_seq=9, record=chain)
    assert item.record == chain
    for kind in ("chain", "lopa", "recommendation", "model_call"):
        api.SupersededRecord(kind=kind, pass_seq=1, superseded_seq=2, record={})
    with pytest.raises(ValidationError):
        api.SupersededRecord(kind="finding", pass_seq=1, superseded_seq=2, record={})
    with pytest.raises(ValidationError):
        api.SupersededRecord(kind="chain", pass_seq=2, superseded_seq=2, record={})


# --- contract v1.8: evidence (Phase 4 plan PR 1) ----------------------------------------------


def test_superseded_kinds_include_evidence_tool_call_and_agent_step() -> None:
    """A re-run supersedes the evidence pass: its records, tool calls and agent steps."""
    for kind in ("evidence", "tool_call", "agent_step"):
        api.SupersededRecord(kind=kind, pass_seq=1, superseded_seq=2, record={})


def _stored(card: dict[str, Any]) -> dict[str, Any]:
    """A shortlist evidence card as stored: without `via_ids`, computed on read (v1.11)."""
    return {k: v for k, v in card.items() if k != "via_ids"}


def _mock_evidence() -> list[dict[str, Any]]:
    items = _fixture("shortlist.json")["items"]
    return [_stored(ev) for item in items for ev in item["evidence"]]


def test_mock_evidence_shows_each_kind_and_verdict() -> None:
    """The mocks show a confirmed calculation with its facts, a skipped calculation naming
    its missing facts, a confirmed precedent with a URL and its judge call, and the
    no-precedent record; no placeholder URL is left."""
    evidence = [Evidence.model_validate(ev) for ev in _mock_evidence()]
    calcs = [e for e in evidence if e.kind == "calculation"]
    precedents = [e for e in evidence if e.kind == "precedent"]
    confirmed_calc = [e for e in calcs if e.verdict == "confirmed"]
    assert confirmed_calc and all(e.fact_ids for e in confirmed_calc)
    skipped = [e for e in calcs if e.verdict == "none" and e.missing_fact_ids]
    assert skipped and all(e.flags for e in skipped)
    found = [e for e in precedents if e.verdict == "confirmed"]
    assert found and all(e.sources and e.model_call_id for e in found)
    assert [e for e in precedents if e.id == ids.no_precedent_evidence_id(e.target_id)]
    for e in calcs:
        key = e.id.rsplit(":", 1)[1]
        calculation, equipment = key.split("-", 1)
        assert e.id == ids.calculation_evidence_id(e.target_id, calculation, equipment)
    for name in ("shortlist.json", "run_dump.json", "demo_response.json"):
        assert "example.org" not in (FIXTURES / name).read_text(encoding="utf-8")


def test_mock_evidence_agrees_across_fixtures() -> None:
    """The run dump and the demo response carry the same evidence records as the shortlist."""
    shortlist = {ev["id"]: ev for ev in _mock_evidence()}
    dump = {ev["id"]: ev for ev in _fixture("run_dump.json")["evidence"]}
    assert dump == shortlist
    demo = _fixture("demo_response.json")["shortlist"]["items"]
    assert {ev["id"]: _stored(ev) for item in demo for ev in item["evidence"]} == shortlist


# --- contract v1.10: the demo landing's start line (deploy plan D0) -----------------------------


def test_a_demo_response_may_name_its_start_line_and_an_older_one_names_none() -> None:
    demo = _fixture("demo_response.json")
    old = {k: v for k, v in demo.items() if k != "start_target_id"}
    assert api.DemoResponse.model_validate(old).start_target_id is None
    target = demo["shortlist"]["items"][0]["target_id"]
    named = api.DemoResponse.model_validate(old | {"start_target_id": target})
    assert named.start_target_id == target


# --- contract v1.11: via, severity definitions, the demo's runs (review plan R0) ----------------


def test_every_shortlist_evidence_card_carries_its_via_ids() -> None:
    items = _fixture("shortlist.json")["items"]
    cards = [ev for item in items for ev in item["evidence"]]
    assert cards and all(ev["via_ids"] == [] for ev in cards)
    card = api.ShortlistEvidence.model_validate(cards[0] | {"via_ids": ["f:x"]})
    assert card.via_ids == ["f:x"]
    stored = {k: v for k, v in card.model_dump(mode="json").items() if k != "via_ids"}
    assert Evidence.model_validate(stored).id == card.id
    assert "via_ids" not in Evidence.model_fields


def test_the_shortlist_serves_the_severity_classes_from_the_reference_table() -> None:
    from guideword.reference import load_reference_set

    served = _fixture("shortlist.json")["severity_classes"]
    table = load_reference_set().severity_classes
    assert served == [
        {"severity_class": r.severity_class.value, "name": r.name, "definition": r.definition}
        for r in table
    ]


def test_the_demo_response_lists_its_runs_with_their_banners() -> None:
    demo = _fixture("demo_response.json")
    parsed = api.DemoResponse.model_validate(demo)
    assert [r.run_id for r in parsed.runs] == [parsed.run.run.id]
    first = parsed.runs[0]
    assert first.plant_id == parsed.plant.plant_id
    assert first.start_target_id == parsed.start_target_id
    with pytest.raises(ValidationError):
        api.DemoResponse.model_validate({k: v for k, v in demo.items() if k != "runs"})
    with pytest.raises(ValidationError):
        api.DemoRun.model_validate({"run_id": "run:x", "plant_id": "p", "extra": 1})
