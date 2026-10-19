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
                "target_id": line["target_id"],
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

    def start(self, cap: float = 1.0, mode: str = "full", plant: str | None = None) -> Any:
        body = {"plant_id": plant or self.plant(), "spend_cap_usd": cap, "mode": mode}
        return self.client.post("/runs", json=body)

    def run_url(self, run_id: str, rest: str = "") -> str:
        return f"/runs/{quote(run_id, safe='')}{rest}"

    def advance(self, run_id: str, secret: str | None = SECRET) -> Any:
        headers = {"X-Internal-Secret": secret} if secret is not None else {}
        url = f"/internal/runs/{quote(run_id, safe='')}/advance"
        return self.client.post(url, headers=headers)

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


def test_the_estimate_is_capped_at_the_spend_cap(tmp_path: Path) -> None:
    app = Api(tmp_path)
    result = app.start(cap=0.01).json()
    assert result["estimated_cost_usd"] == pytest.approx(0.01)


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
