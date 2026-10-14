"""Mock mode (GUIDEWORD_MOCK=1): serves contract/fixtures/ for "Mock Plant A" (spec 0.8).

Every fixture is validated against its response model on load. Events are released over
about 20 seconds counted from the first poll for a run, using the injected clock.
"""

import io
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook  # type: ignore[import-untyped]
from pydantic import BaseModel

from guideword.api import models as api
from guideword.schema.records import Event, Run

DEFAULT_FIXTURES = Path(__file__).resolve().parents[3] / "contract" / "fixtures"
EVENT_RELEASE_SECONDS = 20.0
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
# The Excel worksheet columns (PROJECT.md §5 Step 8), and the WorksheetRow field for each.
WORKSHEET_COLUMNS: list[tuple[str, str]] = [
    ("Section", "section"),
    ("Design intent", "design_intent"),
    ("Guideword", "guideword"),
    ("Parameter", "parameter"),
    ("Deviation", "deviation"),
    ("Causes", "causes"),
    ("Consequences", "consequences"),
    ("Existing safeguards", "existing_safeguards"),
    ("Severity", "severity"),
    ("Likelihood", "likelihood"),
    ("Risk", "risk"),
    ("LOPA gap", "lopa_gap"),
    ("Recommendation", "recommendation"),
    ("Action owner", "action_owner"),
    ("Origin", "origin"),
    ("Evidence", "evidence"),
    ("Status", "status"),
]


def _load[M: BaseModel](directory: Path, model: type[M]) -> M:
    path = directory / api.RESPONSE_FIXTURES[model]
    return model.model_validate(json.loads(path.read_text(encoding="utf-8")))


class MockStore:
    def __init__(self, directory: Path = DEFAULT_FIXTURES) -> None:
        self.plant_list = _load(directory, api.PlantList)
        self.plant_upload_result = _load(directory, api.PlantUploadResult)
        self.plant_detail = _load(directory, api.PlantDetail)
        self.section_proposal = _load(directory, api.SectionProposal)
        self.confirm_sections_result = _load(directory, api.ConfirmSectionsResult)
        self.run_list = _load(directory, api.RunList)
        self.start_run_result = _load(directory, api.StartRunResult)
        self.run_status_result = _load(directory, api.RunStatusResult)
        self.run_detail = _load(directory, api.RunDetail)
        self.events_page = _load(directory, api.EventsPage)
        self.run_sections = _load(directory, api.RunSections)
        self.question_list = _load(directory, api.QuestionList)
        self.question_created = _load(directory, api.QuestionCreated)
        self.shortlist = _load(directory, api.Shortlist)
        self.worksheet = _load(directory, api.Worksheet)
        self.coverage = _load(directory, api.Coverage)
        self.record_detail = _load(directory, api.RecordDetail)
        self.override_result = _load(directory, api.OverrideResult)
        self.run_dump = _load(directory, api.RunDump)
        self.demo_response = _load(directory, api.DemoResponse)
        self.budget = _load(directory, api.Budget)
        self.accepted = _load(directory, api.Accepted)
        self.runs: dict[str, Run] = {run.id: run for run in self.run_list.runs}
        self.plants = {p.plant_record_id: p for p in self.plant_list.plants}
        self._first_poll: dict[str, datetime] = {}

    def events(self, run_id: str, after: int, now: datetime) -> tuple[list[Event], int]:
        """Events with seq > after that have been released by `now`, and the next `after`."""
        first = self._first_poll.setdefault(run_id, now)
        events = self.events_page.events
        elapsed = max(0.0, (now - first).total_seconds())
        fraction = min(1.0, elapsed / EVENT_RELEASE_SECONDS)
        released = min(len(events), 1 + math.floor(fraction * (len(events) - 1)))
        page = [e for e in events if after < e.seq <= released]
        return page, page[-1].seq if page else after


def worksheet_xlsx(rows: list[api.WorksheetRow]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "Worksheet"
    sheet.append([title for title, _ in WORKSHEET_COLUMNS])
    for row in rows:
        values: dict[str, Any] = row.model_dump()
        sheet.append([values[field] for _, field in WORKSHEET_COLUMNS])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
