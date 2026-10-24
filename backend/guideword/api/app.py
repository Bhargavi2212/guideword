"""The Guideword API (PROJECT.md §11 "API contract"), frozen as `contract-v1`.

In mock mode (GUIDEWORD_MOCK=1) every endpoint serves contract/fixtures/. Otherwise the
built endpoints run for real and every other one returns 501 naming the phase that will
build it (NOT_BUILT_PHASE). Run with:
  uvicorn guideword.api.app:create_app --factory
"""

import hmac
from collections.abc import Callable
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Annotated, Any

from fastapi import BackgroundTasks, Body, FastAPI, Header, Request
from fastapi.responses import JSONResponse, Response

from guideword.api import models as api
from guideword.api.live import GatewayFactory, LiveRuns, RunEnded, RunNotFound, UseMismatch
from guideword.api.mock import DEFAULT_FIXTURES, XLSX_MEDIA_TYPE, MockStore, worksheet_xlsx
from guideword.api.suggester import GatewaySuggester
from guideword.config import Config, load_config
from guideword.evidence.step import EvidenceTools
from guideword.gateway.cache import ResponseCache
from guideword.gateway.client import Gateway
from guideword.gateway.ledgers import Ledger, ledger_for
from guideword.gateway.transport import OpenAITransport
from guideword.logs import get_logger
from guideword.reference import ReferenceSet, load_reference_set
from guideword.review.overrides import OverrideRefused
from guideword.runs.case import evidence_tools
from guideword.runs.db import make_session_factory
from guideword.runs.plants import (
    PlantRepository,
    StoredPlant,
    load_plant,
    not_stated_issues,
    plant_facts,
)
from guideword.runs.start import ModeNotBuilt, PlantNotFound, SectionsNotConfirmed, StartMismatch
from guideword.schema import ids
from guideword.schema.enums import (
    BudgetUse,
    Environment,
    PlantStatus,
    QuestionKind,
    QuestionOrigin,
    QuestionStatus,
    RunLabelKind,
    RunStatus,
)
from guideword.schema.records import Override, Question, Run
from guideword.schema.validate import Issue, validate_plant
from guideword.sections.confirm import check_confirmed
from guideword.sections.rules import rule_cut
from guideword.sections.suggest import NullSuggester, Suggester, check_suggestions
from guideword.settings import Settings
from guideword.tools.web import SearchClient, live_search

Clock = Callable[[], datetime]
# live runs started through the API on the laptop spend `development` (R25; Phase 7 sets
# the hosted uses); the phase their calls are booked to
API_RUN_USE = BudgetUse.DEVELOPMENT


def one_gateway_use(use: BudgetUse | None) -> None:
    """Until B2 adds one gateway per use, the API's only gateway spends API_RUN_USE, so a run
    on any other use would be billed to it (Bhargavi, 2026-10-23). B2 removes this refusal
    when it adds the gateways. Raises ApiError 409."""
    if use is not None and use != API_RUN_USE:
        raise ApiError(
            409,
            f"API runs spend use {API_RUN_USE.value} only until per-use gateways arrive in B2; "
            f"use {use.value} is refused",
        )


# runs started through the API spend under Phase 4 (Phase 4 plan Q16): they now make the
# evidence step's judge calls and web searches too
API_RUN_PHASE = "4"
log = get_logger(__name__)

# The phase that builds each endpoint for real (PROJECT.md §15); a 501 names it.
NOT_BUILT_PHASE: dict[tuple[str, str], int] = {
    ("GET", "/demo"): 7,
}
ERRORS: dict[int | str, dict[str, Any]] = {
    code: {"model": api.ErrorBody} for code in (401, 403, 404, 409, 501)
}


def _issues(issues: list[Issue]) -> list[api.Issue]:
    return [api.Issue(code=i.code, object_id=i.object_id, message=i.message) for i in issues]


class ApiError(Exception):
    def __init__(self, status: int, detail: str, phase: int | None = None) -> None:
        super().__init__(detail)
        self.status = status
        self.body = api.ErrorBody(detail=detail, phase=phase)


def create_app(
    *,
    settings: Settings | None = None,
    clock: Clock | None = None,
    fixtures_dir: Path | None = None,
    suggester: Suggester | None = None,
    gateway_factory: GatewayFactory | None = None,
    ledger: Ledger | None = None,
    search: SearchClient | None = None,
) -> FastAPI:
    """`gateway_factory`, `ledger` and `search` are injected by tests (fake gateway, temporary
    ledger, fake web search); by default live runs go through Token Factory, Tavily and this
    environment's ledger. With a fake gateway and no search, evidence is off (Q4 holds for
    the real app: an uploaded plant on use development gets evidence)."""
    settings = settings if settings is not None else Settings()
    now: Clock = clock if clock is not None else (lambda: datetime.now(UTC))
    store = MockStore(fixtures_dir or DEFAULT_FIXTURES) if settings.guideword_mock else None
    app = FastAPI(
        title="Guideword API",
        version="contract-v1",
        description="AI HAZOP preparation. Every run-related response carries a label "
        "(live, recorded or mock). Without mock mode, endpoints return 501 until their phase.",
    )

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, error: ApiError) -> JSONResponse:
        return JSONResponse(status_code=error.status, content=error.body.model_dump())

    def need(method: str, path: str) -> MockStore:
        if store is None:
            phase = NOT_BUILT_PHASE[(method, path)]
            raise ApiError(501, f"not implemented until phase {phase}", phase=phase)
        return store

    def run_of(mock: MockStore, run_id: str) -> Run:
        run = mock.runs.get(run_id)
        if run is None:
            raise ApiError(404, f"no run {run_id}")
        return run

    def plant_of(mock: MockStore, plant_id: str) -> api.PlantSummary:
        plant = mock.plants.get(plant_id)
        if plant is None:
            raise ApiError(404, f"no plant {plant_id}")
        return plant

    # --- plants ---------------------------------------------------------------------------

    # The store and the reference tables are opened on the first plant request, so routes
    # that are not built yet (and the OpenAPI export) never create a database.
    @cache
    def sessions() -> Any:
        return make_session_factory(settings.database_url)

    @cache
    def plant_store() -> PlantRepository:
        return PlantRepository(sessions())

    @cache
    def config() -> Config:
        return load_config(global_budget_usd=settings.global_budget_usd)

    @cache
    def the_ledger() -> Ledger:
        return ledger if ledger is not None else ledger_for(settings, sessions())

    def token_factory(session_factory: Any) -> Gateway:
        return Gateway(
            config=config(),
            transport=OpenAITransport(settings),
            cache=ResponseCache(session_factory),
            ledger=the_ledger(),
            use=API_RUN_USE,
            phase=API_RUN_PHASE,
            clock=now,
        )

    def evidence_factory(session_factory: Any) -> EvidenceTools:
        client = (
            search
            if search is not None
            else live_search(settings.tavily_api_key.get_secret_value())
        )
        return evidence_tools(
            config=config(),
            cache=ResponseCache(session_factory),
            ledger=the_ledger(),
            use=API_RUN_USE,
            phase=API_RUN_PHASE,
            clock=now,
            search=client,
        )

    @cache
    def live() -> LiveRuns:
        evidence_on = gateway_factory is None or search is not None
        return LiveRuns(
            sessions(),
            config=config(),
            ref=reference(),
            gateway_factory=gateway_factory if gateway_factory is not None else token_factory,
            clock=now,
            evidence_factory=evidence_factory if evidence_on else None,
        )

    @cache
    def the_suggester() -> Suggester:
        """The suggester given, else Super through the gateway when one is configured (an
        injected factory or an API key), else none (spec 2.7)."""
        if suggester is not None:
            return suggester
        if gateway_factory is not None or settings.nebius_api_key.get_secret_value():
            return GatewaySuggester(live().gateway(), config())
        return NullSuggester()

    def live_run(run_id: str) -> Run:
        try:
            return live().get(run_id)
        except RunNotFound as missing:
            raise ApiError(404, str(missing)) from missing

    @cache
    def reference() -> ReferenceSet:
        return load_reference_set()

    @app.get("/plants", response_model=api.PlantList, responses=ERRORS)
    def list_plants() -> api.PlantList:
        if store is not None:
            return store.plant_list
        return api.PlantList(
            plants=[
                api.PlantSummary(plant_record_id=r.id, plant_id=r.plant_id, status=r.status)
                for r in plant_store().records()
            ]
        )

    @app.post("/plants", response_model=api.PlantUploadResult, responses=ERRORS)
    def upload_plant(plant_file: Annotated[dict[str, Any], Body()]) -> api.PlantUploadResult:
        if store is not None:
            return store.plant_upload_result
        record, report = load_plant(plant_file, reference())
        if record is None:
            return api.PlantUploadResult(
                plant_record_id=None,
                ok=False,
                errors=_issues(report.errors),
                warnings=_issues(report.warnings),
            )
        facts = plant_facts(record.plant_file, record.id)
        plant_store().add(record, plant_file, facts)
        return api.PlantUploadResult(
            plant_record_id=record.id,
            ok=True,
            errors=[],
            warnings=_issues(report.warnings + not_stated_issues(facts)),
        )

    @app.get("/plants/{id}", response_model=api.PlantDetail, responses=ERRORS)
    def get_plant(id: str) -> api.PlantDetail:
        if store is not None:
            plant_of(store, id)
            return store.plant_detail
        stored = plant_store().get(id)
        if stored is None:
            raise ApiError(404, f"no plant {id}")
        report = validate_plant(stored.raw, reference())
        return api.PlantDetail(
            plant_record_id=stored.record.id,
            plant_id=stored.record.plant_id,
            status=stored.record.status,
            facts=stored.facts,
            warnings=_issues(report.warnings + not_stated_issues(stored.facts)),
            sections=stored.sections,
        )

    def stored_plant(record_id: str) -> StoredPlant:
        stored = plant_store().get(record_id)
        if stored is None:
            raise ApiError(404, f"no plant {record_id}")
        return stored

    @app.post("/plants/{id}/sections/propose", response_model=api.SectionProposal, responses=ERRORS)
    def propose_sections(id: str) -> api.SectionProposal:
        if store is not None:
            plant_of(store, id)
            return store.section_proposal
        plant = stored_plant(id).record.plant_file
        sections = rule_cut(plant, id)
        valid, rejected = check_suggestions(
            plant, sections, the_suggester().suggest(plant, sections)
        )
        for suggestion, reason in rejected:
            log.info(
                "section suggestion rejected",
                extra={
                    "context": {
                        "plant_record_id": id,
                        "suggestion": suggestion.model_dump(mode="json"),
                        "reason": reason,
                    }
                },
            )
        # the rule cut is the plant's current set; a propose after confirm clears it (P5)
        plant_store().set_sections(id, sections, PlantStatus.SECTIONS_PROPOSED)
        return api.SectionProposal(
            plant_record_id=id,
            sections=sections,
            suggestions=valid,
            # what code refused and why, shown to the engineer (contract v1.3, R23)
            rejected=[
                api.RejectedSuggestion(suggestion=suggestion, reason=reason)
                for suggestion, reason in rejected
            ],
        )

    @app.put("/plants/{id}/sections", response_model=api.ConfirmSectionsResult, responses=ERRORS)
    def confirm_sections(id: str, request: api.ConfirmSectionsRequest) -> api.ConfirmSectionsResult:
        if store is not None:
            plant_of(store, id)
            return store.confirm_sections_result
        plant = stored_plant(id).record.plant_file
        issues = check_confirmed(plant, id, request.sections)
        if issues:
            raise ApiError(409, "\n".join(f"{i.code} {i.object_id}: {i.message}" for i in issues))
        plant_store().confirm(id, request.sections)
        return api.ConfirmSectionsResult(
            plant_record_id=id,
            status=PlantStatus.SECTIONS_CONFIRMED,
            section_ids=[s.id for s in request.sections],
        )

    # --- runs -----------------------------------------------------------------------------

    @app.get("/runs", response_model=api.RunList, responses=ERRORS)
    def list_runs() -> api.RunList:
        if store is not None:
            return store.run_list
        return api.RunList(runs=live().runs.records())

    @app.post("/runs", response_model=api.StartRunResult, responses=ERRORS)
    def start_run(request: api.StartRunRequest) -> api.StartRunResult:
        if store is not None:
            plant = plant_of(store, request.plant_id)
            if plant.status != PlantStatus.SECTIONS_CONFIRMED:
                raise ApiError(409, "sections not confirmed")
            for run in store.runs.values():
                if (
                    run.plant_record_id == plant.plant_record_id
                    and run.status == RunStatus.STOPPED_CAP
                    and request.spend_cap_usd <= run.spend_cap_usd
                ):
                    raise ApiError(409, str(ids.CapReachedError()))
            return store.start_run_result
        one_gateway_use(request.use)
        try:
            run, estimate = live().start(
                request.plant_id,
                request.spend_cap_usd,
                request.mode,
                use=request.use,
                post_spend_cap_usd=request.post_spend_cap_usd,
            )
        except PlantNotFound as missing:
            raise ApiError(404, str(missing)) from missing
        except (SectionsNotConfirmed, ModeNotBuilt, ids.CapReachedError, StartMismatch) as refused:
            raise ApiError(409, str(refused)) from refused
        return api.StartRunResult(run_id=run.id, estimated_cost_usd=estimate, label=run.label)

    @app.post("/runs/{id}/cancel", response_model=api.RunStatusResult, responses=ERRORS)
    def cancel_run(id: str) -> api.RunStatusResult:
        if store is not None:
            run = run_of(store, id)
            return api.RunStatusResult(run_id=run.id, status=RunStatus.CANCELLED, label=run.label)
        live_run(id)
        try:
            run = live().cancel(id)
        except RunEnded as ended:
            raise ApiError(409, str(ended)) from ended
        return api.RunStatusResult(run_id=run.id, status=run.status, label=run.label)

    @app.get("/runs/{id}", response_model=api.RunDetail, responses=ERRORS)
    def get_run(id: str) -> api.RunDetail:
        if store is not None:
            run_of(store, id)
            return store.run_detail
        run = live_run(id)
        return api.RunDetail(run=run, counts=live().counts(id), label=run.label)

    @app.get("/runs/{id}/events", response_model=api.EventsPage, responses=ERRORS)
    def get_events(id: str, after: int = 0) -> api.EventsPage:
        if store is not None:
            run = run_of(store, id)
            events, next_after = store.events(run.id, after, now())
            return api.EventsPage(
                run_id=run.id, events=events, next_after=next_after, label=store.events_page.label
            )
        run = live_run(id)
        page = live().runs.events(id, after)
        return api.EventsPage(
            run_id=run.id,
            events=page,
            next_after=page[-1].seq if page else after,
            label=run.label,
        )

    @app.get("/runs/{id}/sections", response_model=api.RunSections, responses=ERRORS)
    def get_run_sections(id: str) -> api.RunSections:
        if store is not None:
            run_of(store, id)
            return store.run_sections
        run = live_run(id)
        return api.RunSections(run_id=run.id, sections=live().runs.sections(id), label=run.label)

    @app.get("/runs/{id}/questions", response_model=api.QuestionList, responses=ERRORS)
    def get_questions(
        id: str,
        kind: QuestionKind | None = None,
        status: QuestionStatus | None = None,
        section_id: str | None = None,
    ) -> api.QuestionList:
        if store is not None:
            run_of(store, id)
            source = store.question_list.questions
            label = store.question_list.label
            run_id = store.question_list.run_id
        else:
            run = live_run(id)
            source, label, run_id = live().runs.questions(id), run.label, run.id
        questions = [
            q
            for q in source
            if (kind is None or q.kind == kind)
            and (status is None or q.status == status)
            and (section_id is None or q.section_id == section_id)
        ]
        return api.QuestionList(run_id=run_id, questions=questions, label=label)

    @app.post("/runs/{id}/questions", response_model=api.QuestionCreated, responses=ERRORS)
    def add_question(id: str, request: api.AddQuestionRequest) -> api.QuestionCreated:
        if store is not None:
            run = run_of(store, id)
            if request.section_id not in {s.id for s in store.run_sections.sections}:
                raise ApiError(404, f"no section {request.section_id} in run {run.id}")
            question = Question(
                id=ids.engineer_question_id(request.section_id, request.text),
                run_id=run.id,
                kind=QuestionKind.ENGINEER,
                origin=QuestionOrigin.ENGINEER,
                status=QuestionStatus.OPEN,
                section_id=request.section_id,
                text=request.text,
            )
            return api.QuestionCreated(question=question, label=store.question_created.label)
        run = live_run(id)
        try:
            question = live().add_question(id, request.section_id, request.text)
        except RunNotFound as missing:
            raise ApiError(404, str(missing)) from missing
        return api.QuestionCreated(question=question, label=run.label)

    @app.get("/runs/{id}/shortlist", response_model=api.Shortlist, responses=ERRORS)
    def get_shortlist(id: str) -> api.Shortlist:
        if store is not None:
            run_of(store, id)
            return store.shortlist
        run = live_run(id)
        return api.Shortlist(run_id=run.id, items=live().shortlist(id), label=run.label)

    def worksheet_of(id: str) -> api.Worksheet:
        if store is not None:
            run_of(store, id)
            return store.worksheet
        run = live_run(id)
        return api.Worksheet(run_id=run.id, rows=live().worksheet(id), label=run.label)

    @app.get("/runs/{id}/worksheet", response_model=api.Worksheet, responses=ERRORS)
    def get_worksheet(
        id: str, origin: str | None = None, status: str | None = None
    ) -> api.Worksheet:
        sheet = worksheet_of(id)
        rows = [
            row
            for row in sheet.rows
            if (origin is None or row.origin == origin) and (status is None or row.status == status)
        ]
        return sheet.model_copy(update={"rows": rows})

    @app.get("/runs/{id}/coverage", response_model=api.Coverage, responses=ERRORS)
    def get_coverage(id: str) -> api.Coverage:
        if store is not None:
            run_of(store, id)
            return store.coverage
        run = live_run(id)
        lines, failed = live().coverage(id)
        return api.Coverage(run_id=run.id, lists=lines, failed_question_ids=failed, label=run.label)

    @app.get("/runs/{id}/records/{record_id}", response_model=api.RecordDetail, responses=ERRORS)
    def get_record(id: str, record_id: str) -> api.RecordDetail:
        if store is not None:
            run_of(store, id)
            detail = store.records.get(record_id)
            if detail is None:
                raise ApiError(404, f"no record {record_id}")
            return detail
        run = live_run(id)
        try:
            found, model_calls, tool_calls = live().record(id, record_id)
        except RunNotFound as missing:
            raise ApiError(404, str(missing)) from missing
        return api.RecordDetail(
            run_id=run.id,
            record_id=record_id,
            record_kind=found.kind,
            record=found.record,
            parent_ids=found.parent_ids,
            model_calls=model_calls,
            tool_calls=tool_calls,
            label=run.label,
        )

    @app.post("/runs/{id}/overrides", response_model=api.OverrideResult, responses=ERRORS)
    def add_override(id: str, request: api.OverrideRequest) -> api.OverrideResult:
        if store is None:
            run = live_run(id)
            if run.label.kind == RunLabelKind.RECORDED:
                raise ApiError(403, "recorded run is read-only")
            try:
                stored = live().add_override(id, request, now())
            except OverrideRefused as refused:
                raise ApiError(refused.status, str(refused)) from refused
            return api.OverrideResult(override=stored, stored=True, label=run.label)
        run = run_of(store, id)
        if run.label.kind == RunLabelKind.RECORDED:
            raise ApiError(403, "recorded run is read-only")
        override = Override(
            id=ids.override_id(request.target_id, request.action, request.new_value),
            run_id=run.id,
            target_id=request.target_id,
            action=request.action,
            new_value=request.new_value,
            reason=request.reason,
            by=request.by,
            at=now(),
        )
        return api.OverrideResult(override=override, stored=False, label=run.label)

    @app.get(
        "/runs/{id}/export.xlsx",
        response_class=Response,
        responses={**ERRORS, 200: {"content": {XLSX_MEDIA_TYPE: {}}}},
    )
    def export_worksheet(id: str) -> Response:
        # one row per worksheet row, overrides applied (spec 3.5)
        rows = worksheet_of(id).rows
        return Response(content=worksheet_xlsx(rows), media_type=XLSX_MEDIA_TYPE)

    @app.get("/runs/{id}/export/coverage.json", response_model=api.Coverage, responses=ERRORS)
    def export_coverage(id: str) -> api.Coverage:
        return get_coverage(id)

    @app.get("/runs/{id}/export/run.json", response_model=api.RunDump, responses=ERRORS)
    def export_run(id: str) -> api.RunDump:
        if store is not None:
            run_of(store, id)
            return store.run_dump
        live_run(id)
        return live().dump(id)

    # --- demo, budget, internal --------------------------------------------------------------

    @app.get("/demo", response_model=api.DemoResponse, responses=ERRORS)
    def get_demo() -> api.DemoResponse:
        return need("GET", "/demo").demo_response

    @app.get("/budget", response_model=api.Budget, responses=ERRORS)
    def get_budget() -> api.Budget:
        # this environment's line only, from its own ledger (R25); the opening balance counts as
        # spent, as in scripts/budget_status.py (a comment, not a docstring: the contract)
        if store is not None:
            return store.budget
        environment = Environment(settings.guideword_env)
        entries = [e for e in the_ledger().entries() if e.environment == environment]
        by_model: dict[str, float] = {}
        for entry in entries:
            if entry.kind == "model" and entry.model:
                by_model[entry.model] = by_model.get(entry.model, 0.0) + entry.cost_usd
        spent = sum(e.cost_usd for e in entries)
        allowance = config().caps.environment_allowance(environment)
        return api.Budget(
            environments=[
                api.EnvironmentBudget(
                    environment=environment.value,
                    allowance_usd=allowance,
                    spent_usd=round(spent, 6),
                    remaining_usd=round(allowance - spent, 6),
                )
            ],
            by_model=[
                api.ModelSpend(model=m, spent_usd=round(v, 6)) for m, v in sorted(by_model.items())
            ],
            # the live-run button is Phase 7; on the laptop it is never available (R25)
            live_run_available=False,
            message=None,
        )

    @app.post(
        "/internal/runs/{id}/advance",
        status_code=202,
        response_model=api.Accepted,
        responses=ERRORS,
    )
    def advance_run(
        id: str,
        background: BackgroundTasks,
        x_internal_secret: Annotated[str | None, Header(alias="X-Internal-Secret")] = None,
        request: api.AdvanceRequest | None = None,
    ) -> api.Accepted:
        # one advance; while the run is still running, the next ones run in-process after the
        # response (the laptop loop; the hosted chaining is Phase 7)
        expected = settings.internal_advance_secret.get_secret_value()
        given = x_internal_secret or ""
        if not expected or not hmac.compare_digest(given.encode(), expected.encode()):
            raise ApiError(401, "missing or wrong X-Internal-Secret")
        if store is not None:
            run_of(store, id)
            return store.accepted
        run = live_run(id)
        named = request.use if request is not None else None
        one_gateway_use(run.use if run.use is not None else named)
        try:
            live().name_use(id, named)
        except UseMismatch as refused:
            raise ApiError(409, str(refused)) from refused
        if live().advance_once(id) == RunStatus.RUNNING:
            background.add_task(live().drive, id)
        return api.Accepted(accepted=True)

    return app
