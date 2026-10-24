"""The run endpoints without mock mode (spec 2.8; plan PR 10, R20, R21, R25). Fake gateway only:
a scripted model drives a whole run of the §9 example through the advance route."""

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from guideword.api import models as api
from guideword.api.app import NOT_BUILT_PHASE, create_app
from guideword.config import load_config
from guideword.gateway.client import Gateway
from guideword.gateway.fake import fake_gateway, reply
from guideword.gateway.ledgers import LaptopLedger
from guideword.gateway.transport import Reply, ToolCallRequest
from guideword.runs.db import EventRow, make_session_factory
from guideword.runs.store import RunRepository
from guideword.schema.enums import BudgetUse, EventType
from guideword.schema.records import SpendEntry
from guideword.settings import Settings

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
NOW = datetime(2026, 10, 17, 9, 0, tzinfo=UTC)
SECRET = "test-advance-secret"
BUILT_IN_PR_10 = {
    ("GET", "/runs"),
    ("POST", "/runs"),
    ("POST", "/runs/{id}/cancel"),
    ("GET", "/runs/{id}"),
    ("GET", "/runs/{id}/events"),
    ("GET", "/runs/{id}/sections"),
    ("GET", "/runs/{id}/questions"),
    ("POST", "/runs/{id}/questions"),
    ("GET", "/runs/{id}/coverage"),
    ("GET", "/runs/{id}/records/{record_id}"),
    ("GET", "/budget"),
    ("POST", "/internal/runs/{id}/advance"),
}
_BLOCK = r"<{0}>\s*(.*?)\s*</{0}>"


def _block(request: dict[str, Any], name: str) -> Any:
    match = re.search(_BLOCK.format(name), request["messages"][0]["content"], re.S)
    assert match is not None, name
    return json.loads(match.group(1))


def script(job: str, request: dict[str, Any]) -> Reply:
    """The orchestrator drains every open list and finishes; each specialist gives one
    outside-library finding per question on the first location of its context; severity
    rates every finding S3; the screen names one hypothesis on a location; the post-analysis
    jobs find nothing to add."""
    if job == "section_suggestion":
        return reply({"suggestions": []})
    if job == "plant_screen":
        location = _block(request, "plant")["locations"][0]["id"]
        hypothesis = {
            "rank": 1,
            "mechanism": "something outside hits the building",
            "component_ids": [location],
            "chemical_ids": [],
            "failing_component_type": "external",
            "cause_id": "outside_library",
            "cause_text": "something outside",
            "consequence": "a release",
            "reason": "test",
        }
        return reply({"hypotheses": [hypothesis]})
    if job == "orchestrator":
        view = _block(request, "view")
        agents = sorted(view["open"])
        if agents:
            retry = view["retry_at_hard"].get(agents[0], {"count": 0})["count"]
            level = "bulk" if view["open"][agents[0]]["count"] > retry else "hard"
            name, args = "dispatch_specialist", {"agent": agents[0], "level": level}
        else:
            name, args = "finish", {}
        return reply(tool_calls=(ToolCallRequest("t", name, json.dumps({"reason": "go", **args})),))
    if job == "severity_reason":
        return reply(
            {
                "severities": [
                    {"finding_id": f["finding_id"], "severity_class": "S3", "reason": "one hurt"}
                    for f in _block(request, "findings")
                ]
            }
        )
    # the post-analysis jobs (Phase 3, plan G14): no chains, no layer applies, no action
    if job == "connector":
        return reply({"chains": []})
    if job == "chain_severity":
        return reply({"severities": []})
    if job == "lopa_argument":
        lines = [
            {
                "target": line["handle"],
                "layers": [
                    {"layer_id": layer["layer_id"], "applies": False, "reason": "no"}
                    for layer in line["layers"]
                ],
            }
            for line in _block(request, "lines")
        ]
        return reply({"lines": lines})
    if job == "recommendation":
        return reply({"recommendations": []})
    locations = _block(request, "context").get("locations") or []
    questions = _block(request, "questions")
    if not locations:
        answers = [
            {"question_id": q["id"], "not_credible": {"reason": "no location"}, "findings": []}
            for q in questions
        ]
    else:
        answers = [
            {
                "question_id": q["id"],
                "not_credible": None,
                "findings": [
                    {
                        "cause_id": "outside_library",
                        "cause_text": "something outside",
                        "failing_component_type": "external",
                        "failing_component_ids": [locations[0]["id"]],
                        "consequence": "a release",
                        "safeguard_ids": [],
                        "adequacy": "unknown",
                        "confidence": "sure",
                        "reason": "test",
                    }
                ],
            }
            for q in questions
        ]
    return reply({"answers": answers, "added_questions": []})


class Api:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp = tmp_path
        self.ledger = LaptopLedger(tmp_path / "ledger.jsonl")
        self.settings = Settings(
            _env_file=None,  # type: ignore[call-arg]
            guideword_mock=False,
            database_url=f"sqlite:///{(tmp_path / 'g.db').as_posix()}",
            internal_advance_secret=SECRET,
        )
        config = load_config(global_budget_usd=25.0)

        def gateway(sessions: sessionmaker[Session]) -> Gateway:
            built, _ = fake_gateway(
                config,
                script,
                sessions=sessions,
                ledger_path=tmp_path / "ledger.jsonl",
                clock=lambda: NOW,
            )
            return built

        factory: Callable[[sessionmaker[Session]], Gateway] = gateway
        self.client = TestClient(
            create_app(
                settings=self.settings,
                clock=lambda: NOW,
                gateway_factory=factory,
                ledger=self.ledger,
            )
        )

    def plant(self, confirm: bool = True) -> str:
        data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        record_id = self.client.post("/plants", json=data).json()["plant_record_id"]
        url = f"/plants/{quote(record_id, safe='')}"
        proposal = self.client.post(f"{url}/sections/propose").json()
        if confirm:
            put = self.client.put(f"{url}/sections", json={"sections": proposal["sections"]})
            assert put.status_code == 200, put.text
        return str(record_id)

    def start(
        self,
        cap: float = 1.0,
        mode: str = "full",
        plant: str | None = None,
        *,
        use: str = "development",
        post_cap: float = 0.3,
    ) -> Any:
        body = {
            "plant_id": plant or self.plant(),
            "spend_cap_usd": cap,
            "mode": mode,
            "use": use,
            "post_spend_cap_usd": post_cap,
        }
        return self.client.post("/runs", json=body)

    def run_url(self, run_id: str, rest: str = "") -> str:
        return f"/runs/{quote(run_id, safe='')}{rest}"

    def advance(self, run_id: str, secret: str | None = SECRET, use: str | None = None) -> Any:
        headers = {"X-Internal-Secret": secret} if secret is not None else {}
        url = f"/internal/runs/{quote(run_id, safe='')}/advance"
        body = {"use": use} if use is not None else None
        return self.client.post(url, headers=headers, json=body)

    def runs(self) -> RunRepository:
        return RunRepository(make_session_factory(self.settings.database_url), lambda: NOW)

    def finished_run(self) -> str:
        run_id = str(self.start().json()["run_id"])
        assert self.advance(run_id).status_code == 202
        return run_id


@pytest.fixture
def app(tmp_path: Path) -> Api:
    return Api(tmp_path)


def test_the_built_routes_left_not_built_phase() -> None:
    assert not BUILT_IN_PR_10 & set(NOT_BUILT_PHASE)


def test_start_returns_a_live_run_and_an_upper_bound_capped_at_the_cap(app: Api) -> None:
    response = app.start(cap=1000.0)
    assert response.status_code == 200, response.text
    result = api.StartRunResult.model_validate(response.json())
    assert result.label.kind == "live"
    assert 0 < result.estimated_cost_usd < 1000.0  # the real upper bound, under a huge cap


def test_the_estimate_is_the_analysis_capped_at_the_spend_cap_plus_the_post_cap(
    tmp_path: Path,
) -> None:
    """Bhargavi, 2026-10-20 (point 4): the upper bound is the worst case, so it includes the
    post-analysis cap the run may also spend."""
    app = Api(tmp_path)
    result = app.start(cap=0.01).json()
    post_cap = load_config(global_budget_usd=25.0).caps.run.post_spend_cap_usd
    assert post_cap > 0
    assert result["estimated_cost_usd"] == pytest.approx(0.01 + post_cap)


def test_sample_mode_is_refused_until_phase_7(app: Api) -> None:
    response = app.start(mode="sample")
    assert response.status_code == 409 and "Phase 7" in response.json()["detail"]


def test_an_unconfirmed_or_unknown_plant_is_refused(app: Api) -> None:
    unconfirmed = app.plant(confirm=False)
    assert app.start(plant=unconfirmed).status_code == 409
    assert app.start(plant="plant:nope:0").status_code == 404


def test_advance_needs_the_secret_and_drives_the_run_to_its_end(app: Api) -> None:
    run_id = app.start().json()["run_id"]
    assert app.advance(run_id, secret=None).status_code == 401
    assert app.advance(run_id, secret="wrong").status_code == 401
    assert app.advance(run_id).status_code == 202
    detail = api.RunDetail.model_validate(app.client.get(app.run_url(run_id)).json())
    assert detail.label.kind == "live"
    assert detail.run.status == "finished"
    assert detail.counts.questions_open == 0
    assert (
        detail.counts.questions_total
        == detail.counts.questions_checked + detail.counts.questions_failed
    )
    assert detail.counts.findings > 0 and detail.counts.chains == 0


def test_list_and_unknown_runs(app: Api) -> None:
    run_id = app.finished_run()
    runs = api.RunList.model_validate(app.client.get("/runs").json())
    assert [r.id for r in runs.runs] == [run_id]
    for rest in ("", "/events", "/sections", "/questions", "/coverage", "/records/x"):
        assert app.client.get(app.run_url("run:nope", rest)).status_code == 404, rest
    assert app.advance("run:nope").status_code == 404


def test_events_page_by_sequence(app: Api) -> None:
    run_id = app.finished_run()
    page = api.EventsPage.model_validate(app.client.get(app.run_url(run_id, "/events")).json())
    assert page.events and page.label.kind == "live"
    assert page.next_after == page.events[-1].seq
    again = app.client.get(app.run_url(run_id, f"/events?after={page.next_after}")).json()
    assert again["events"] == [] and again["next_after"] == page.next_after


def test_sections_questions_and_coverage(app: Api) -> None:
    run_id = app.finished_run()
    sections = api.RunSections.model_validate(
        app.client.get(app.run_url(run_id, "/sections")).json()
    )
    assert sections.sections and sections.label.kind == "live"
    questions = api.QuestionList.model_validate(
        app.client.get(app.run_url(run_id, "/questions")).json()
    )
    pairs = app.client.get(app.run_url(run_id, "/questions?kind=chemical_pair")).json()
    assert pairs["questions"] and {q["kind"] for q in pairs["questions"]} == {"chemical_pair"}
    coverage = api.Coverage.model_validate(app.client.get(app.run_url(run_id, "/coverage")).json())
    # every list but `sections` (which counts sections) counts questions
    per_kind = [line for line in coverage.lists if line.list != "sections"]
    assert sum(line.total for line in per_kind) == len(questions.questions)
    assert coverage.label.kind == "live"


def test_an_engineer_question_joins_as_open_once(app: Api) -> None:
    run_id = app.finished_run()
    section = app.client.get(app.run_url(run_id, "/sections")).json()["sections"][0]["id"]
    body = {"section_id": section, "text": "What if the agitator runs backwards?"}
    first = api.QuestionCreated.model_validate(
        app.client.post(app.run_url(run_id, "/questions"), json=body).json()
    )
    assert first.question.id.startswith("eng:") and first.question.status == "open"
    assert first.label.kind == "live"
    second = app.client.post(app.run_url(run_id, "/questions"), json=body).json()
    assert second["question"]["id"] == first.question.id
    stored = app.client.get(app.run_url(run_id, "/questions?status=open")).json()["questions"]
    assert [q["id"] for q in stored] == [first.question.id]
    missing = app.client.post(app.run_url(run_id, "/questions"), json=body | {"section_id": "S-NO"})
    assert missing.status_code == 404


def test_record_detail_for_a_finding_and_a_hypothesis(app: Api) -> None:
    run_id = app.finished_run()
    run_dump = app.client.get(app.run_url(run_id, "/events")).json()["events"]
    assert run_dump
    from guideword.runs.db import make_session_factory  # noqa: PLC0415
    from guideword.runs.store import RunRepository  # noqa: PLC0415

    runs = RunRepository(make_session_factory(app.settings.database_url), lambda: NOW)
    finding = runs.findings(run_id)[0]
    detail = api.RecordDetail.model_validate(
        app.client.get(app.run_url(run_id, f"/records/{quote(finding.id, safe='')}")).json()
    )
    assert (detail.record_kind, detail.parent_ids) == ("finding", [finding.question_id])
    assert [c.id for c in detail.model_calls] == [finding.model_call_id]
    hypothesis = runs.hypotheses(run_id)[0]
    hyp = app.client.get(app.run_url(run_id, f"/records/{quote(hypothesis.id, safe='')}")).json()
    assert hyp["record_kind"] == "hypothesis" and hyp["parent_ids"] == [hypothesis.model_call_id]
    assert [c["id"] for c in hyp["model_calls"]] == [hypothesis.model_call_id]


def test_cancel_stops_a_run_and_a_finished_run_cannot_be_cancelled(app: Api) -> None:
    run_id = app.start().json()["run_id"]
    result = api.RunStatusResult.model_validate(
        app.client.post(app.run_url(run_id, "/cancel")).json()
    )
    assert result.status == "cancelled" and result.label.kind == "live"
    assert app.advance(run_id).status_code == 202
    assert app.client.get(app.run_url(run_id)).json()["run"]["status"] == "cancelled"
    done = app.finished_run()
    assert app.client.post(app.run_url(done, "/cancel")).status_code == 409


def test_budget_shows_this_environment_only_from_its_own_ledger(app: Api) -> None:
    app.ledger.append(
        SpendEntry(
            ts=NOW,
            kind="model",
            environment="laptop",
            phase="2",
            use="development",
            model="nvidia/x",
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.25,
            script="test",
            purpose="test",
        )
    )
    budget = api.Budget.model_validate(app.client.get("/budget").json())
    assert [e.environment for e in budget.environments] == ["laptop"]
    [laptop] = budget.environments
    assert (laptop.allowance_usd, laptop.spent_usd) == (19.0, 0.25)
    assert laptop.remaining_usd == pytest.approx(18.75)
    assert [(m.model, m.spent_usd) for m in budget.by_model] == [("nvidia/x", 0.25)]
    assert budget.live_run_available is False


# --- a run's use and post cap are fixed when it starts (contract v1.9, Q4, Q12) ---------------


def _set_use(app: Api, run_id: str, use: str | None) -> None:
    """As a run started by a script on another use, or stored before v1.9 (None)."""
    with app.runs().step(run_id) as writer:
        writer.set_use(None if use is None else BudgetUse(use))


def test_start_needs_a_use_and_a_post_cap(app: Api) -> None:
    body = {"plant_id": app.plant(), "spend_cap_usd": 1.0, "mode": "full"}
    assert app.client.post("/runs", json=body).status_code == 422
    assert app.client.post("/runs", json=body | {"use": "development"}).status_code == 422


def test_a_run_records_the_use_it_started_with(app: Api) -> None:
    run_id = app.start(post_cap=0.1).json()["run_id"]
    run = app.runs().get(run_id)
    assert run is not None
    assert (run.use, run.post_spend_cap_usd) == ("development", 0.1)


def test_a_resume_naming_another_use_or_post_cap_is_409(app: Api) -> None:
    plant = app.plant()
    run_id = app.start(plant=plant, post_cap=0.1).json()["run_id"]
    other_cap = app.start(plant=plant, post_cap=0.3)
    assert other_cap.status_code == 409 and "0.1" in other_cap.json()["detail"]
    _set_use(app, run_id, "video")
    other_use = app.start(plant=plant, post_cap=0.1)
    assert other_use.status_code == 409 and "video" in other_use.json()["detail"]


def test_an_advance_naming_another_use_is_409(app: Api) -> None:
    run_id = app.start().json()["run_id"]
    refused = app.advance(run_id, use="test_5")
    assert refused.status_code == 409 and "development" in refused.json()["detail"]
    assert app.advance(run_id, use="development").status_code == 202


def test_a_run_with_no_use_names_one_on_its_first_advance_and_keeps_it(app: Api) -> None:
    """A run stored before v1.9 has no use: no default; the first advance names it."""
    run_id = app.start().json()["run_id"]
    _set_use(app, run_id, None)
    refused = app.advance(run_id)
    assert refused.status_code == 409 and "name one" in refused.json()["detail"]
    assert app.advance(run_id, use="development").status_code == 202
    assert app.runs().get(run_id).use == "development"  # type: ignore[union-attr]


# --- until B2, API runs spend development only (Bhargavi, 2026-10-23) ------------------------


def test_until_b2_a_start_naming_another_use_is_409(app: Api) -> None:
    refused = app.start(use="video")
    assert refused.status_code == 409
    assert "B2" in refused.json()["detail"] and "development" in refused.json()["detail"]
    assert app.client.get("/runs").json()["runs"] == []


def test_until_b2_a_run_on_another_use_is_never_advanced_through_the_api(app: Api) -> None:
    """A run a script started on video would otherwise be billed to development here."""
    run_id = app.start().json()["run_id"]
    _set_use(app, run_id, "video")
    refused = app.advance(run_id)
    assert refused.status_code == 409 and "B2" in refused.json()["detail"]
    assert app.runs().get(run_id).status == "running"  # type: ignore[union-attr]
    assert app.runs().model_calls(run_id) == []


def test_until_b2_a_run_with_no_use_cannot_name_another_on_advance(app: Api) -> None:
    run_id = app.start().json()["run_id"]
    _set_use(app, run_id, None)
    refused = app.advance(run_id, use="video")
    assert refused.status_code == 409 and "B2" in refused.json()["detail"]
    assert app.runs().get(run_id).use is None  # type: ignore[union-attr]


# --- events served typed; stored events get their tier on read (contract v1.9, C3, H14) -------


def _store_legacy_event(app: Api, run_id: str, type: str, payload: dict[str, Any]) -> int:
    """An event as stored before v1.9: no stamp. Written straight to the table."""
    sessions = make_session_factory(app.settings.database_url)
    with sessions.begin() as session:
        seq = 1 + max(r.seq for r in session.query(EventRow).filter_by(run_id=run_id))
        record = {"run_id": run_id, "seq": seq, "type": type, "payload": payload}
        session.add(
            EventRow(run_id=run_id, seq=seq, type=type, record=record | {"time": NOW.isoformat()})
        )
    return seq


def _served(app: Api, run_id: str, seq: int) -> dict[str, Any]:
    events = app.client.get(app.run_url(run_id, "/events")).json()["events"]
    [event] = [e for e in events if e["seq"] == seq]
    return dict(event)


LEGACY_CALL = {
    "model_call_id": "mc:aaaaaaaaaaaaaaaa",
    "job": "specialist_bulk",
    "cache_hit": False,
    "outcome": "ok",
    "cost_usd": 0.0,
    "cap_cost_usd": 0.0,
}


def test_a_stored_model_call_gets_its_tier_inferred_on_read_and_never_written_back(
    app: Api,
) -> None:
    config = load_config(global_budget_usd=25.0)
    lightning = config.models.tiers["lightning"].expected_id
    run_id = app.finished_run()
    seq = _store_legacy_event(app, run_id, "model_call", LEGACY_CALL | {"model_id": lightning})
    served = _served(app, run_id, seq)
    assert served["payload_schema"] is None
    assert (served["payload"]["tier"], served["payload"]["tier_source"]) == (
        "lightning",
        "inferred",
    )
    [stored] = [e for e in app.runs().events(run_id) if e.seq == seq]
    assert "tier" not in stored.payload and "tier_source" not in stored.payload


def test_a_stored_model_call_with_an_unknown_model_shows_no_tier(app: Api) -> None:
    run_id = app.finished_run()
    seq = _store_legacy_event(app, run_id, "model_call", LEGACY_CALL | {"model_id": "gone/model"})
    payload = _served(app, run_id, seq)["payload"]
    assert (payload["tier"], payload["tier_source"]) == (None, None)


def test_a_stored_dispatch_gets_its_tier_from_its_runs_routing_config(app: Api) -> None:
    run_id = app.finished_run()
    dispatch = {
        "agent": "process",
        "level": "hard",
        "question_ids": [],
        "selected_by_code": True,
        "skipped": [],
        "batches": 0,
    }
    seq = _store_legacy_event(app, run_id, "dispatch", dispatch)
    run = app.runs().get(run_id)
    assert run is not None
    expected = run.routing_config["specialist_hard"]
    payload = _served(app, run_id, seq)["payload"]
    assert (payload["tier"], payload["tier_source"]) == (expected, "inferred")


def test_new_events_carry_their_recorded_tier(app: Api) -> None:
    run_id = app.finished_run()
    events = app.client.get(app.run_url(run_id, "/events")).json()["events"]
    calls = [e for e in events if e["type"] in ("model_call", "dispatch")]
    assert calls and all(e["payload"]["tier_source"] == "recorded" for e in calls)
    assert all(e["payload_schema"] == "v1.9" for e in events)


def test_an_event_written_flagged_is_served_with_its_flag(
    app: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A live run writes an event whose payload fails its model, flagged (2026-10-23)."""
    run_id = app.finished_run()
    monkeypatch.setattr("guideword.runs.store.STRICT_PAYLOADS", False)
    with app.runs().step(run_id) as writer:
        event = writer.emit(EventType.STEP_STARTED, {"step": "ranked", "odd": 1})
    served = _served(app, run_id, event.seq)
    assert served["payload_invalid"] is True and served["payload_error"]
    assert served["payload"] == {"step": "ranked", "odd": 1}
