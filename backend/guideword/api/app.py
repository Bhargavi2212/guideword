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

from fastapi import Body, FastAPI, Header, Request
from fastapi.responses import JSONResponse, Response

from guideword.api import models as api
from guideword.api.mock import DEFAULT_FIXTURES, XLSX_MEDIA_TYPE, MockStore, worksheet_xlsx
from guideword.logs import get_logger
from guideword.reference import ReferenceSet, load_reference_set
from guideword.runs.db import make_session_factory
from guideword.runs.plants import (
    PlantRepository,
    StoredPlant,
    load_plant,
    not_stated_issues,
    plant_facts,
)
from guideword.schema import ids
from guideword.schema.enums import (
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

Clock = Callable[[], datetime]
log = get_logger(__name__)

# The phase that builds each endpoint for real (PROJECT.md §15); a 501 names it.
NOT_BUILT_PHASE: dict[tuple[str, str], int] = {
    ("GET", "/runs"): 2,
    ("POST", "/runs"): 2,
    ("POST", "/runs/{id}/cancel"): 2,
    ("GET", "/runs/{id}"): 2,
    ("GET", "/runs/{id}/events"): 2,
    ("GET", "/runs/{id}/sections"): 2,
    ("GET", "/runs/{id}/questions"): 2,
    ("POST", "/runs/{id}/questions"): 2,
    ("GET", "/runs/{id}/shortlist"): 3,
    ("GET", "/runs/{id}/worksheet"): 3,
    ("GET", "/runs/{id}/coverage"): 2,
    ("GET", "/runs/{id}/records/{record_id}"): 2,
    ("POST", "/runs/{id}/overrides"): 3,
    ("GET", "/runs/{id}/export.xlsx"): 3,
    ("GET", "/runs/{id}/export/coverage.json"): 3,
    ("GET", "/runs/{id}/export/run.json"): 3,
    ("GET", "/demo"): 7,
    ("GET", "/budget"): 2,
    ("POST", "/internal/runs/{id}/advance"): 2,
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
) -> FastAPI:
    settings = settings if settings is not None else Settings()
    # Phase 1 has no live suggester; Phase 2 passes the gateway one
    suggester = suggester if suggester is not None else NullSuggester()
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
    def plant_store() -> PlantRepository:
        return PlantRepository(make_session_factory(settings.database_url))

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
        valid, rejected = check_suggestions(plant, sections, suggester.suggest(plant, sections))
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
        return api.SectionProposal(plant_record_id=id, sections=sections, suggestions=valid)

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
        return need("GET", "/runs").run_list

    @app.post("/runs", response_model=api.StartRunResult, responses=ERRORS)
    def start_run(request: api.StartRunRequest) -> api.StartRunResult:
        mock = need("POST", "/runs")
        plant = plant_of(mock, request.plant_id)
        if plant.status != PlantStatus.SECTIONS_CONFIRMED:
            raise ApiError(409, "sections not confirmed")
        for run in mock.runs.values():
            if (
                run.plant_record_id == plant.plant_record_id
                and run.status == RunStatus.STOPPED_CAP
                and request.spend_cap_usd <= run.spend_cap_usd
            ):
                raise ApiError(409, str(ids.CapReachedError()))
        return mock.start_run_result

    @app.post("/runs/{id}/cancel", response_model=api.RunStatusResult, responses=ERRORS)
    def cancel_run(id: str) -> api.RunStatusResult:
        mock = need("POST", "/runs/{id}/cancel")
        run = run_of(mock, id)
        return api.RunStatusResult(run_id=run.id, status=RunStatus.CANCELLED, label=run.label)

    @app.get("/runs/{id}", response_model=api.RunDetail, responses=ERRORS)
    def get_run(id: str) -> api.RunDetail:
        mock = need("GET", "/runs/{id}")
        run_of(mock, id)
        return mock.run_detail

    @app.get("/runs/{id}/events", response_model=api.EventsPage, responses=ERRORS)
    def get_events(id: str, after: int = 0) -> api.EventsPage:
        mock = need("GET", "/runs/{id}/events")
        run = run_of(mock, id)
        events, next_after = mock.events(run.id, after, now())
        return api.EventsPage(
            run_id=run.id, events=events, next_after=next_after, label=mock.events_page.label
        )

    @app.get("/runs/{id}/sections", response_model=api.RunSections, responses=ERRORS)
    def get_run_sections(id: str) -> api.RunSections:
        mock = need("GET", "/runs/{id}/sections")
        run_of(mock, id)
        return mock.run_sections

    @app.get("/runs/{id}/questions", response_model=api.QuestionList, responses=ERRORS)
    def get_questions(
        id: str,
        kind: QuestionKind | None = None,
        status: QuestionStatus | None = None,
        section_id: str | None = None,
    ) -> api.QuestionList:
        mock = need("GET", "/runs/{id}/questions")
        run_of(mock, id)
        questions = [
            q
            for q in mock.question_list.questions
            if (kind is None or q.kind == kind)
            and (status is None or q.status == status)
            and (section_id is None or q.section_id == section_id)
        ]
        return mock.question_list.model_copy(update={"questions": questions})

    @app.post("/runs/{id}/questions", response_model=api.QuestionCreated, responses=ERRORS)
    def add_question(id: str, request: api.AddQuestionRequest) -> api.QuestionCreated:
        mock = need("POST", "/runs/{id}/questions")
        run = run_of(mock, id)
        if request.section_id not in {s.id for s in mock.run_sections.sections}:
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
        return api.QuestionCreated(question=question, label=mock.question_created.label)

    @app.get("/runs/{id}/shortlist", response_model=api.Shortlist, responses=ERRORS)
    def get_shortlist(id: str) -> api.Shortlist:
        mock = need("GET", "/runs/{id}/shortlist")
        run_of(mock, id)
        return mock.shortlist

    @app.get("/runs/{id}/worksheet", response_model=api.Worksheet, responses=ERRORS)
    def get_worksheet(
        id: str, origin: str | None = None, status: str | None = None
    ) -> api.Worksheet:
        mock = need("GET", "/runs/{id}/worksheet")
        run_of(mock, id)
        rows = [
            row
            for row in mock.worksheet.rows
            if (origin is None or row.origin == origin) and (status is None or row.status == status)
        ]
        return mock.worksheet.model_copy(update={"rows": rows})

    @app.get("/runs/{id}/coverage", response_model=api.Coverage, responses=ERRORS)
    def get_coverage(id: str) -> api.Coverage:
        mock = need("GET", "/runs/{id}/coverage")
        run_of(mock, id)
        return mock.coverage

    @app.get("/runs/{id}/records/{record_id}", response_model=api.RecordDetail, responses=ERRORS)
    def get_record(id: str, record_id: str) -> api.RecordDetail:
        mock = need("GET", "/runs/{id}/records/{record_id}")
        run_of(mock, id)
        if record_id != mock.record_detail.record_id:
            raise ApiError(404, f"no record {record_id}")
        return mock.record_detail

    @app.post("/runs/{id}/overrides", response_model=api.OverrideResult, responses=ERRORS)
    def add_override(id: str, request: api.OverrideRequest) -> api.OverrideResult:
        mock = need("POST", "/runs/{id}/overrides")
        run = run_of(mock, id)
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
        mock = need("GET", "/runs/{id}/export.xlsx")
        run_of(mock, id)
        return Response(content=worksheet_xlsx(mock.worksheet.rows), media_type=XLSX_MEDIA_TYPE)

    @app.get("/runs/{id}/export/coverage.json", response_model=api.Coverage, responses=ERRORS)
    def export_coverage(id: str) -> api.Coverage:
        mock = need("GET", "/runs/{id}/export/coverage.json")
        run_of(mock, id)
        return mock.coverage

    @app.get("/runs/{id}/export/run.json", response_model=api.RunDump, responses=ERRORS)
    def export_run(id: str) -> api.RunDump:
        mock = need("GET", "/runs/{id}/export/run.json")
        run_of(mock, id)
        return mock.run_dump

    # --- demo, budget, internal --------------------------------------------------------------

    @app.get("/demo", response_model=api.DemoResponse, responses=ERRORS)
    def get_demo() -> api.DemoResponse:
        return need("GET", "/demo").demo_response

    @app.get("/budget", response_model=api.Budget, responses=ERRORS)
    def get_budget() -> api.Budget:
        return need("GET", "/budget").budget

    @app.post(
        "/internal/runs/{id}/advance",
        status_code=202,
        response_model=api.Accepted,
        responses=ERRORS,
    )
    def advance_run(
        id: str,
        x_internal_secret: Annotated[str | None, Header(alias="X-Internal-Secret")] = None,
    ) -> api.Accepted:
        expected = settings.internal_advance_secret.get_secret_value()
        given = x_internal_secret or ""
        if not expected or not hmac.compare_digest(given.encode(), expected.encode()):
            raise ApiError(401, "missing or wrong X-Internal-Secret")
        mock = need("POST", "/internal/runs/{id}/advance")
        run_of(mock, id)
        return mock.accepted

    return app
