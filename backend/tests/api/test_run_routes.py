"""The run endpoints without mock mode (spec 2.8; plan PR 10, R20, R21, R25). Fake gateway only:
a scripted model drives a whole run of the §9 example through the advance route."""

import json
import re
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from guideword.api import models as api
from guideword.api.app import API_RUN_PHASE, NOT_BUILT_PHASE, create_app
from guideword.api.live import LiveRuns
from guideword.config import load_config
from guideword.gateway.client import Gateway
from guideword.gateway.fake import fake_gateway, reply
from guideword.gateway.ledgers import LaptopLedger
from guideword.gateway.transport import Reply, ToolCallRequest
from guideword.reference import load_reference_set
from guideword.runs.case import start_case
from guideword.runs.db import EventRow, make_session_factory
from guideword.runs.store import RunRepository
from guideword.schema.enums import BudgetUse, EventType, RunStatus
from guideword.schema.records import SpendEntry
from guideword.settings import Settings

# Phase 9 (spec 9.1): the card every plant_screen/v4 hypothesis carries
SCREEN_CARD: dict[str, Any] = {
    "initiating_event": "test",
    "enabling_condition": "test",
    "propagation": "test",
    "consequence_magnitude": None,
    "operating_mode": "normal",
    "mechanism_class": "other",
    "fact_ids": [],
}


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
            **SCREEN_CARD,
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
    def __init__(self, tmp_path: Path, env: str = "laptop") -> None:
        self.tmp = tmp_path
        self.ledger = LaptopLedger(tmp_path / "ledger.jsonl")
        self.settings = Settings(
            _env_file=None,  # type: ignore[call-arg]
            guideword_mock=False,
            database_url=f"sqlite:///{(tmp_path / 'g.db').as_posix()}",
            internal_advance_secret=SECRET,
            guideword_env=env,
        )
        config = load_config(global_budget_usd=25.0)

        def gateway(sessions: sessionmaker[Session], use: BudgetUse) -> Gateway:
            built, _ = fake_gateway(
                config,
                script,
                sessions=sessions,
                ledger_path=tmp_path / "ledger.jsonl",
                clock=lambda: NOW,
                use=use,
                phase=API_RUN_PHASE,
                ledger=self.ledger,
            )
            return built

        factory: Callable[[sessionmaker[Session], BudgetUse], Gateway] = gateway
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
        # B2: spend cap + post cap fits Phase 5's cap (Q10)
        cap: float = 0.2,
        mode: str = "full",
        plant: str | None = None,
        *,
        use: str = "development",
        post_cap: float = 0.1,
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
    response = app.start()
    assert response.status_code == 200, response.text
    result = api.StartRunResult.model_validate(response.json())
    assert result.label.kind == "live"
    # the real upper bound under a huge cap: the API refuses such a cap since B2, so it is
    # asked of LiveRuns, which computes the estimate
    (app.tmp / "huge").mkdir()
    other = Api(app.tmp / "huge")
    live = _live_runs(other, Blocking())
    _, estimate = live.start(
        other.plant(), 1000.0, "full", use=BudgetUse.DEVELOPMENT, post_spend_cap_usd=0.1
    )
    assert 0 < estimate < 1000.0


def test_the_estimate_is_the_analysis_capped_at_the_spend_cap_plus_the_post_cap(
    tmp_path: Path,
) -> None:
    """Bhargavi, 2026-10-20 (point 4): the upper bound is the worst case, so it includes the
    post-analysis cap the run may also spend."""
    app = Api(tmp_path)
    # B2: the post cap is the request's (Q10, Q11)
    result = app.start(cap=0.01, post_cap=0.1).json()
    assert result["estimated_cost_usd"] == pytest.approx(0.01 + 0.1)


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
    # an API start drives its run to the end (B2), so the running run is started in the store
    _, run_id = _live(app, Blocking())
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


def _spend(app: Api, use: str, phase: str, cost: float) -> None:
    app.ledger.append(
        SpendEntry(
            ts=NOW,
            kind="model",
            environment="laptop",
            phase=phase,
            use=use,
            model="nvidia/x",
            input_tokens=1,
            output_tokens=1,
            cost_usd=cost,
            script="test",
            purpose="test",
        )
    )


def test_budget_lists_each_use_and_the_api_run_phase_with_what_remains(app: Api) -> None:
    """Contract v1.9 (C6, G6, H7): this environment's uses, the API runs' phase cap, and the
    uses API runs may take, each read the way the gateway checks them."""
    config = load_config(global_budget_usd=25.0)
    _spend(app, "development", "2", 0.25)
    _spend(app, "video", API_RUN_PHASE, 0.5)
    _spend(app, "development", API_RUN_PHASE, 0.125)
    budget = api.Budget.model_validate(app.client.get("/budget").json())
    uses = {u.use: u for u in budget.uses}
    assert set(uses) == {"development", "test_5", "benchmark", "video"}  # laptop's only
    development = uses["development"]
    assert (development.allowance_usd, development.spent_usd) == (4.14, 0.375)
    assert development.remaining_usd == pytest.approx(3.765)
    assert uses["video"].remaining_usd == pytest.approx(1.5)
    assert uses["test_5"].spent_usd == 0.0
    phase = budget.api_run_phase
    assert phase.phase == API_RUN_PHASE
    assert phase.cap_usd == config.caps.phase_caps_usd[API_RUN_PHASE]
    assert phase.spent_usd == pytest.approx(0.625)
    assert phase.remaining_usd == pytest.approx(phase.cap_usd - 0.625)
    assert budget.api_run_uses == ["development", "video"]


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
    # a running run to resume: an API start drives its run to the end (B2)
    live, run_id = _live(app, Blocking())
    plant = live.get(run_id).plant_record_id
    other_cap = app.start(plant=plant, post_cap=0.2)
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


# --- B2: UI-started laptop runs are driven in-process, each on its own use ------------------


def test_a_run_started_through_the_api_reaches_finished_with_no_further_request(
    app: Api,
) -> None:
    run_id = app.start().json()["run_id"]
    assert app.runs().get(run_id).status == "finished"  # type: ignore[union-attr]


def test_a_run_is_driven_with_its_own_use(app: Api) -> None:
    """B2 removes the interim refusal (2026-10-23): a video run starts, and its calls bill
    video, on the API runs' phase."""
    run_id = app.start(use="video").json()["run_id"]
    assert app.runs().get(run_id).status == "finished"  # type: ignore[union-attr]
    # the run's own lines (the plant's section suggestion spends development, acceptance 5)
    lines = [e for e in app.ledger.entries() if e.kind == "model" and run_id in e.purpose]
    assert lines and {e.use for e in lines} == {"video"}
    assert {e.phase for e in lines} == {"5"}


def test_api_runs_charge_phase_5() -> None:
    assert API_RUN_PHASE == "5"


def test_start_refuses_a_use_not_offered_to_api_runs(app: Api) -> None:
    refused = app.start(use="test_5")
    assert refused.status_code == 409 and "test_5" in refused.json()["detail"]
    assert app.client.get("/runs").json()["runs"] == []


def test_start_refuses_a_maximum_above_the_uses_remaining_amount(app: Api) -> None:
    _spend(app, "video", "4", 1.9)  # video's $2.00 leaves $0.10
    refused = app.start(use="video", cap=0.15, post_cap=0.10)
    detail = refused.json()["detail"]
    assert refused.status_code == 409 and "use video" in detail and "0.1" in detail
    assert app.client.get("/runs").json()["runs"] == []


def test_start_refuses_a_maximum_above_the_phases_remaining_cap(app: Api) -> None:
    _spend(app, "development", API_RUN_PHASE, 0.40)  # phase 5's $0.50 leaves $0.10
    refused = app.start(cap=0.15, post_cap=0.10)
    detail = refused.json()["detail"]
    assert refused.status_code == 409 and f"phase {API_RUN_PHASE}" in detail
    # the plant's section suggestion spent a little of the phase too
    assert app.start(cap=0.04, post_cap=0.04).status_code == 200


def test_a_hosted_app_never_starts_or_drives_a_laptop_use(tmp_path: Path) -> None:
    """Hosted runs are Phase 7: a laptop use is not one of the hosted environment's, so the
    start is refused before any run exists, and nothing is driven."""
    hosted = Api(tmp_path, env="hosted")
    refused = hosted.start()
    assert refused.status_code == 409 and "hosted" in refused.json()["detail"]
    assert hosted.client.get("/runs").json()["runs"] == []


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


# --- B2 (P5-2): one driver per run; cancel stops a background drive ----------------------------


class Blocking:
    """The test model, held at its first plant-screen call until released."""

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()

    def __call__(self, job: str, request: dict[str, Any]) -> Reply:
        if job == "plant_screen" and not self.entered.is_set():
            self.entered.set()
            assert self.release.wait(10)
        return script(job, request)


def _live_runs(app: Api, model: Blocking) -> LiveRuns:
    """A LiveRuns on the app's store, with the test model."""
    config = load_config(global_budget_usd=25.0)
    sessions = make_session_factory(app.settings.database_url)

    def gateway(s: sessionmaker[Session], use: BudgetUse) -> Gateway:
        built, _ = fake_gateway(
            config, model, sessions=s, ledger_path=app.tmp / "l2.jsonl", clock=lambda: NOW, use=use
        )
        return built

    return LiveRuns(
        sessions,
        config=config,
        ref=load_reference_set(),
        gateway_factory=gateway,
        clock=lambda: NOW,
    )


def _live(app: Api, model: Blocking) -> tuple[LiveRuns, str]:
    """A LiveRuns on the app's store, and a running run started in it (not driven), with the
    caps `Api.start` uses."""
    live = _live_runs(app, model)
    run = start_case(
        live.plants,
        live.runs,
        live.ref,
        live.config,
        app.plant(),
        0.2,
        use=BudgetUse.DEVELOPMENT,
        post_spend_cap_usd=0.1,
    )
    return live, run.id


def test_two_drives_of_one_run_never_step_it_at_once(app: Api) -> None:
    model = Blocking()
    live, run_id = _live(app, model)
    first = threading.Thread(target=live.drive, args=(run_id,))
    first.start()
    assert model.entered.wait(10)
    # the run is mid-step in the first driver: a second drive and a step return at once
    assert live.drive(run_id) == RunStatus.RUNNING
    assert live.step_once(run_id) is None
    model.release.set()
    first.join(10)
    assert live.get(run_id).status == RunStatus.FINISHED
    screens = [c for c in live.runs.model_calls(run_id) if c.job == "plant_screen"]
    assert len({c.id for c in screens}) == len(screens)


def test_cancel_stops_a_background_drive(app: Api) -> None:
    model = Blocking()
    live, run_id = _live(app, model)
    driver = threading.Thread(target=live.drive, args=(run_id,))
    driver.start()
    assert model.entered.wait(10)
    live.cancel(run_id)
    model.release.set()
    driver.join(10)
    assert not driver.is_alive()
    assert live.get(run_id).status == RunStatus.CANCELLED


# --- B3 (P5-6): every timeline entry opens in the record drawer --------------------------------

# the payload keys that name a record the drawer can open
RECORD_KEYS = (
    "finding_id",
    "hypothesis_id",
    "chain_id",
    "lopa_id",
    "evidence_id",
    "model_call_id",
    "tool_call_id",
    "step_id",
)


def _record(app: Api, run_id: str, record_id: str) -> Any:
    return app.client.get(app.run_url(run_id, f"/records/{quote(record_id, safe='')}"))


def test_record_detail_returns_a_tool_call_with_its_step(app: Api) -> None:
    run_id = app.finished_run()
    events = app.client.get(app.run_url(run_id, "/events")).json()["events"]
    tool_call_id = next(e["payload"]["tool_call_id"] for e in events if e["type"] == "tool_call")
    response = _record(app, run_id, tool_call_id)
    assert response.status_code == 200, response.text
    detail = api.RecordDetail.model_validate(response.json())
    assert detail.record_kind == "tool_call"
    assert detail.record["id"] == tool_call_id
    step_id = detail.record["agent_step_id"]
    assert detail.parent_ids == [step_id]
    assert [t.id for t in detail.tool_calls] == [tool_call_id]
    assert _record(app, run_id, step_id).status_code == 200


def test_every_timeline_entry_of_a_fake_run_is_addressable(app: Api) -> None:
    """Each record an event names opens in the drawer (P5-6); an event that names none is a
    step boundary, a coverage line, a cap or the run's start or end."""
    run_id = app.finished_run()
    events = app.client.get(app.run_url(run_id, "/events")).json()["events"]
    named = {e["payload"][k] for e in events for k in RECORD_KEYS if k in e["payload"]}
    assert any(r.startswith("tc:") for r in named) and any(r.startswith("mc:") for r in named)
    missing = [r for r in sorted(named) if _record(app, run_id, r).status_code != 200]
    assert missing == []
