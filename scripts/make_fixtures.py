"""Write the run-scoped contract fixtures from $0 fake runs (Phase 5 plan B1, C5, G3, Q2).

  python scripts/make_fixtures.py            # write contract/fixtures/
  python scripts/make_fixtures.py --check    # exit 1 if regenerating would change a file

Three runs of Mock Plant A go through the real API with mock mode off, on a temporary store
and ledger, with a scripted fake gateway, a fake web search and an empty precedent index:

- the main run, scripted to cover every case the hand-built fixtures showed (plan table F);
- a cancelled run (the next attempt), for `run_status_result.json`;
- a failing run (the attempt after it), for `events_page_failed.json`.

Time is frozen: the clock starts at 2026-10-13T10:00:00Z and moves one second per read, and
the fake gateway's timer reads 0. After the runs, exactly two stamps are applied (plan H12):
every run label becomes `mock`, and the override result reads `stored: false`, as the mock
server echoes overrides without storing them. Nothing else is edited. The plant's fixtures
(its upload result, detail, list, section proposal and confirmation) come from the same API
session (Bhargavi, 2026-10-24); the plant file itself, `budget.json` and `accepted.json` stay
hand-written. `demo_response.json` is assembled from the generated plant, run and shortlist.

No live call is possible: the gateway's transport is a script, the search is a script, and
`budget/ledger.jsonl` and `guideword.db` are never opened.
"""

import argparse
import json
import re
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi.testclient import TestClient
from guideword.api.app import create_app
from guideword.config import Config, load_config
from guideword.gateway.client import Gateway
from guideword.gateway.fake import fake_gateway, reply
from guideword.gateway.ledgers import LaptopLedger
from guideword.gateway.transport import Reply, ToolCallRequest
from guideword.reference.precedents import PrecedentIndex
from guideword.runs.db import ResponseCacheRow, make_session_factory
from guideword.runs.extend import extend
from guideword.runs.store import RunRepository
from guideword.settings import Settings
from guideword.tools.web import FakeSearch
from pydantic import SecretStr
from sqlalchemy import delete
from sqlalchemy.orm import Session, sessionmaker

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "contract" / "fixtures"
PLANT_FILE = FIXTURES / "mock_plant_a.json"
SECRET = "fixture-generator-secret"
START = datetime(2026, 10, 13, 10, 0, tzinfo=UTC)
USE = "development"
SPEND_CAP_USD = 1.0
# small enough that the first post-analysis call stops the run at its post cap, so the run
# shows a cap stop and its resume (plan Q2); the resume raises it to POST_CAP_USD
FIRST_POST_CAP_USD = 0.000001
POST_CAP_USD = 0.30
REVIEWER = "Mock reviewer"
# the Super section suggestions the scripted model makes (shown, not applied: the confirmed set
# is the rule cut)
SUGGESTIONS = [
    {
        "kind": "purpose",
        "section_ids": ["S-MX-1"],
        "purpose": "Blends Si-H fluid and KOH solution, steam heated",
        "reason": "MX-1 receives both chemicals and the steam heat source.",
    },
    {
        "kind": "split",
        # the rule cut splits L-12 at P-1 already; this splits the pumped part at HV-12
        "section_ids": ["S-L-12~P-1", "S-L-12~HV-12"],
        "purpose": None,
        "reason": "Downstream of HV-12 the line is isolated from P-1 whenever HV-12 is closed.",
    },
]
_BLOCK = r"<{0}>\s*(.*?)\s*</{0}>"

# what the main run's specialists answer, by question (plan table F)
FINDINGS: dict[str, dict[str, Any]] = {
    "m:S-MX-1:more:temperature": {
        "cause_id": "C01",
        "cause_text": None,
        "failing_component_type": "control_loop",
        "failing_component_ids": ["TV-1"],
        "consequence": "MX-1 overheats and hot liquid is released inside the building.",
        "safeguard_ids": ["SG-TRIP"],
        "adequacy": "adequate",
        "confidence": "sure",
    },
    "pair:KOH:SIH": {
        "cause_id": "C14",
        "cause_text": None,
        "failing_component_type": "operator",
        "failing_component_ids": ["P-CHARGE-1"],
        "consequence": "KOH meets the Si-H fluid and hydrogen builds up in the building.",
        "safeguard_ids": ["SG-VENT"],
        "adequacy": "inadequate",
        "confidence": "unsure",
    },
    "m:S-L-12:reverse:flow": {
        "cause_id": "C20",
        "cause_text": None,
        "failing_component_type": "pipe",
        "failing_component_ids": ["L-12"],
        "consequence": "Caustic mix flows back to the tote and splashes the operator.",
        "safeguard_ids": [],
        "adequacy": "unknown",
        "confidence": "unsure",
    },
    "relief:PSV-1": {
        "cause_id": "outside_library",
        "cause_text": "PSV-1 lifts and vents hydrogen at the roof",
        "failing_component_type": "relief_device",
        "failing_component_ids": ["PSV-1"],
        "consequence": "A flammable release at the roof ignites next to workers.",
        "safeguard_ids": [],
        "adequacy": "unknown",
        # first answered unsure; the orchestrator sends it to Ultra, which answers sure
        "confidence": "unsure",
    },
}
# the one question the orchestrator sends for an Ultra re-answer (an Ultra-tier finding)
REANSWER = ("process", "relief:PSV-1")
NOT_CREDIBLE = {
    "m:S-MX-1:more:pressure": (
        "PSV-1 is sized for the steam case and no other source can pressurise MX-1 above its "
        "set pressure."
    ),
}
# every other question is not credible: an answer needs a finding or a not-credible reason
DEFAULT_NOT_CREDIBLE = "Scripted for Mock Plant A: not credible here."
# its batch answers with text that is not JSON, alone too: the question ends failed
FAILS = {"work:W-1:PSV-1"}
SEVERITY = {
    "m:S-MX-1:more:temperature": ("S2", "Hot liquid release inside an occupied building."),
    "pair:KOH:SIH": ("S3", "Flammable gas in an occupied building with ignition sources."),
    "m:S-L-12:reverse:flow": ("S4", "Caustic splash on an operator at the charging point."),
    "relief:PSV-1": ("S3", "Ignition of a flammable release next to workers on the roof."),
}
HYPOTHESES = [
    {
        "rank": 1,
        "mechanism": "The wrong tote is charged and KOH meets the Si-H fluid in MX-1.",
        "component_ids": ["P-CHARGE-1"],
        "chemical_ids": ["KOH", "SIH"],
        "failing_component_type": "operator",
        "cause_id": "C14",
        "cause_text": "wrong tote selected",
        "consequence": "Hydrogen in an occupied building.",
        "reason": "The charging step selects the tote by its label only.",
    },
    {
        "rank": 2,
        "mechanism": "A fire outside the building heats the roof vent line.",
        "component_ids": ["BLDG-1"],
        "chemical_ids": [],
        "failing_component_type": "external",
        "cause_id": "C22",
        "cause_text": "external fire",
        "consequence": "A release at the roof.",
        "reason": "Hot work on the roof is planned.",
    },
    {
        "rank": 3,
        "mechanism": "A tank that is not in the plant overflows.",
        "component_ids": ["TANK-9"],
        "chemical_ids": [],
        "failing_component_type": "tank",
        "cause_id": "C21",
        "cause_text": "overfill",
        "consequence": "A spill.",
        "reason": "Dropped by code: TANK-9 is not a plant object.",
    },
]
CHAIN = {
    "description": "Wrong tote charged; the hydrogen it makes leaves by PSV-1 at the roof.",
    "reason": "The pair finding's gas is what PSV-1 vents.",
}
RECOMMENDATION = "Add a tote identity check before P-1 can start."
# The precedent comes from the fake web search, not the index: the code labels index rows as
# CSB investigations, and no fixture may name a real source. The index is empty.
WEB_PRECEDENT = {
    "title": "Mock precedent: a steam control valve stuck open overheated a batch mixer",
    "url": "https://precedent.mock.invalid/MP-0001",
    "content": "Mock: a steam control valve failed open and a batch mixer overheated.",
}
EMPTY_INDEX = PrecedentIndex((), "mock-empty-index")


class Clock:
    """Frozen time that moves one second per read."""

    def __init__(self) -> None:
        self._now = START

    def __call__(self) -> datetime:
        now = self._now
        self._now += timedelta(seconds=1)
        return now


@dataclass
class Script:
    """The fake model. `fail_orchestrator` makes the failing run's orchestrator answer with
    text that is not JSON, twice, so the run fails."""

    fail_orchestrator: bool = False
    sent: list[str] = field(default_factory=list)

    def __call__(self, job: str, request: dict[str, Any]) -> Reply:
        self.sent.append(job)
        handler = getattr(self, f"_{job}", None)
        if handler is not None:
            result: Reply = handler(request)
            return result
        return self._specialist(request)

    def _section_suggestion(self, request: dict[str, Any]) -> Reply:
        return reply({"suggestions": SUGGESTIONS})

    def _plant_screen(self, request: dict[str, Any]) -> Reply:
        return reply({"hypotheses": HYPOTHESES})

    def _orchestrator(self, request: dict[str, Any]) -> Reply:
        if self.fail_orchestrator:
            return reply("not json")
        view = _block(request, "view")
        agents = sorted(view["open"])
        agent, question = REANSWER
        if agents:
            retry = view["retry_at_hard"].get(agents[0], {"count": 0})["count"]
            level = "bulk" if view["open"][agents[0]]["count"] > retry else "hard"
            name, args = "dispatch_specialist", {"agent": agents[0], "level": level}
        elif question in view["unsure"]["ids"]:
            name = "dispatch_specialist"
            args = {"agent": agent, "level": "unsure", "question_ids": [question]}
        else:
            name, args = "finish", {}
        call = ToolCallRequest("t", name, json.dumps({"reason": "next open list", **args}))
        return reply(tool_calls=(call,))

    def _unsure_answer(self, request: dict[str, Any]) -> Reply:
        """Ultra's re-answer: the same finding, now sure."""
        questions = _block(request, "questions")
        answers = [
            {
                "question_id": q["id"],
                "not_credible": None,
                "findings": [FINDINGS[q["id"]] | {"confidence": "sure", "reason": "scripted"}],
            }
            for q in questions
        ]
        return reply({"answers": answers, "added_questions": []})

    def _specialist(self, request: dict[str, Any]) -> Reply:
        questions = _block(request, "questions")
        if any(q["id"] in FAILS for q in questions):
            return reply("not json")
        answers = []
        for q in questions:
            finding = FINDINGS.get(q["id"])
            if finding is None:
                answers.append(
                    {
                        "question_id": q["id"],
                        "not_credible": {"reason": NOT_CREDIBLE.get(q["id"], DEFAULT_NOT_CREDIBLE)},
                        "findings": [],
                    }
                )
            else:
                answers.append(
                    {
                        "question_id": q["id"],
                        "not_credible": None,
                        "findings": [finding | {"reason": "scripted"}],
                    }
                )
        return reply({"answers": answers, "added_questions": []})

    def _severity_reason(self, request: dict[str, Any]) -> Reply:
        rated = []
        for f in _block(request, "findings"):
            question = next((q for q in SEVERITY if f["finding_id"].startswith(f"f:{q}:")), "")
            grade, why = SEVERITY.get(question, ("S3", "scripted"))
            rated.append({"finding_id": f["finding_id"], "severity_class": grade, "reason": why})
        return reply({"severities": rated})

    def _connector(self, request: dict[str, Any]) -> Reply:
        # the prompt shows handles, not finding IDs: pick the lines by their failing component
        lines = {
            tuple(line["failing_component_ids"]): line["handle"]
            for line in _block(request, "scenarios")
        }
        pair, relief = lines.get(("P-CHARGE-1",)), lines.get(("PSV-1",))
        if pair is None or relief is None:
            return reply({"chains": []})
        return reply({"chains": [{"links": [pair, relief], **CHAIN}]})

    def _chain_severity(self, request: dict[str, Any]) -> Reply:
        chains = _block(request, "chains")
        return reply(
            {
                "severities": [
                    {"chain": c["handle"], "severity_class": "S3", "reason": CHAIN["reason"]}
                    for c in chains
                ]
            }
        )

    def _lopa_argument(self, request: dict[str, Any]) -> Reply:
        # SG-TRIP is argued and applies; every other layer is left unargued (no credit)
        lines = []
        for line in _block(request, "lines"):
            layers = [
                {
                    "layer_id": layer["layer_id"],
                    "applies": True,
                    "reason": "TS-2 trips XV-STM on high temperature, apart from TIC-1.",
                }
                for layer in line["layers"]
                if layer["layer_id"] == "SG-TRIP"
            ]
            lines.append({"target": line["handle"], "layers": layers})
        return reply({"lines": lines})

    def _recommendation(self, request: dict[str, Any]) -> Reply:
        items = [
            {"target": line["handle"], "action": RECOMMENDATION, "reason": CHAIN["reason"]}
            for line in _block(request, "lines")
        ]
        return reply({"recommendations": items})

    def _precedent_judge(self, request: dict[str, Any]) -> Reply:
        judgements = [
            {
                "candidate": c["handle"],
                "same_mechanism": True,
                "is_incident": True,
                "incident_reason": "Mock: an event in which a mixer overheated.",
                "reason": "Same mechanism (mock): a steam control valve stuck open.",
            }
            for c in _block(request, "candidates")
            # the mock precedent, on the overheating line only
            if WEB_PRECEDENT["title"] in json.dumps(c)
            and "overheats" in json.dumps(_block(request, "line"))
        ]
        return reply({"judgements": judgements})


def _block(request: dict[str, Any], name: str) -> Any:
    match = re.search(_BLOCK.format(name), request["messages"][0]["content"], re.S)
    if match is None:
        raise KeyError(f"no <{name}> block in the request")
    return json.loads(match.group(1))


class Generator:
    def __init__(self, work: Path) -> None:
        self.clock = Clock()
        self.script = Script()
        self.config: Config = load_config(global_budget_usd=25.0)
        self.settings = Settings(
            _env_file=None,
            guideword_mock=False,
            database_url=f"sqlite:///{(work / 'fixtures.db').as_posix()}",
            internal_advance_secret=SecretStr(SECRET),
        )
        ledger_path = work / "ledger.jsonl"
        self.sessions = make_session_factory(self.settings.database_url)

        def gateway(sessions: sessionmaker[Session]) -> Gateway:
            built, _ = fake_gateway(
                self.config,
                self.script,
                sessions=sessions,
                ledger_path=ledger_path,
                clock=self.clock,
                phase="5",
            )
            return built

        factory: Callable[[sessionmaker[Session]], Gateway] = gateway
        self.client = TestClient(
            create_app(
                settings=self.settings,
                clock=self.clock,
                gateway_factory=factory,
                ledger=LaptopLedger(ledger_path),
                search=FakeSearch(lambda query, n: {"results": [WEB_PRECEDENT]}),
                precedent_index=EMPTY_INDEX,
            )
        )

    def runs(self) -> RunRepository:
        return RunRepository(self.sessions, self.clock)

    def get(self, path: str) -> Any:
        response = self.client.get(path)
        if response.status_code != 200:
            raise RuntimeError(f"GET {path}: {response.status_code} {response.text}")
        return response.json()

    def post(self, path: str, body: Any = None, headers: dict[str, str] | None = None) -> Any:
        response = self.client.post(path, json=body, headers=headers or {})
        if response.status_code not in (200, 202):
            raise RuntimeError(f"POST {path}: {response.status_code} {response.text}")
        return response.json()

    def plant(self) -> tuple[str, dict[str, Any]]:
        """Upload Mock Plant A, propose and confirm its sections; the plant fixtures."""
        data = json.loads(PLANT_FILE.read_text(encoding="utf-8"))
        uploaded = self.post("/plants", data)
        record_id = str(uploaded["plant_record_id"])
        url = f"/plants/{quote(record_id, safe='')}"
        proposal = self.post(f"{url}/sections/propose")
        response = self.client.put(f"{url}/sections", json={"sections": proposal["sections"]})
        if response.status_code != 200:
            raise RuntimeError(f"PUT sections: {response.text}")
        files = {
            "plant_upload_result.json": uploaded,
            "section_proposal.json": proposal,
            "confirm_sections_result.json": response.json(),
            "plant_detail.json": self.get(url),
            "plant_list.json": self.get("/plants"),
        }
        return record_id, files

    def start(self, plant: str, post_cap: float) -> Any:
        body = {
            "plant_id": plant,
            "spend_cap_usd": SPEND_CAP_USD,
            "mode": "full",
            "use": USE,
            "post_spend_cap_usd": post_cap,
        }
        return self.post("/runs", body)

    def advance(self, run_id: str) -> None:
        self.post(
            f"/internal/runs/{quote(run_id, safe='')}/advance",
            headers={"X-Internal-Secret": SECRET},
        )

    def run_path(self, run_id: str, rest: str = "") -> str:
        return f"/runs/{quote(run_id, safe='')}{rest}"

    def build(self) -> dict[str, Any]:
        plant, plant_files = self.plant()
        started = self.start(plant, FIRST_POST_CAP_USD)
        run_id = str(started["run_id"])
        self.advance(run_id)
        # the run stopped at its post cap: extended with a higher one, it resumes and ends
        extend(self.runs(), run_id, POST_CAP_USD, self.config)
        self.advance(run_id)
        detail = self.get(self.run_path(run_id))
        if detail["run"]["status"] != "finished":
            raise RuntimeError(f"the main run ended {detail['run']['status']}")
        out: dict[str, Any] = {**plant_files, "start_run_result.json": started}
        created = self.post(
            self.run_path(run_id, "/questions"),
            {"section_id": "S-L-12", "text": "Can HV-12 be left open with P-1 stopped?"},
        )
        out["question_created.json"] = created
        findings = self.get(self.run_path(run_id, "/export/run.json"))["findings"]
        pair = next(f["id"] for f in findings if f["question_id"] == "pair:KOH:SIH")
        # the override goes on the Ultra re-answer, which leads no line: no LOPA it touches
        reanswer = next(
            f["id"] for f in findings if f["question_id"] == "relief:PSV-1" and f["tier"] == "ultra"
        )
        out["override_result.json"] = self.post(
            self.run_path(run_id, "/overrides"),
            {
                "target_id": reanswer,
                "action": "change_severity",
                "new_value": {"severity_class": "S4"},
                "reason": "The building is occupied on every shift.",
                "by": REVIEWER,
            },
        )
        out["run_detail.json"] = self.get(self.run_path(run_id))
        out["events_page.json"] = self.get(self.run_path(run_id, "/events?after=0"))
        out["run_sections.json"] = self.get(self.run_path(run_id, "/sections"))
        out["question_list.json"] = self.get(self.run_path(run_id, "/questions"))
        out["shortlist.json"] = self.get(self.run_path(run_id, "/shortlist"))
        out["worksheet.json"] = self.get(self.run_path(run_id, "/worksheet"))
        out["coverage.json"] = self.get(self.run_path(run_id, "/coverage"))
        out["run_dump.json"] = self.get(self.run_path(run_id, "/export/run.json"))
        out["record_detail.json"] = self.get(
            self.run_path(run_id, f"/records/{quote(pair, safe='')}")
        )
        hypothesis = next(h["id"] for h in out["run_dump.json"]["hypotheses"] if h["rank"] == 1)
        out["record_detail_hypothesis.json"] = self.get(
            self.run_path(run_id, f"/records/{quote(hypothesis, safe='')}")
        )
        # the next attempt, cancelled; and the one after it, failing
        cancelled = str(self.start(plant, POST_CAP_USD)["run_id"])
        out["run_status_result.json"] = self.post(self.run_path(cancelled, "/cancel"))
        self.script.fail_orchestrator = True
        # identical requests would be served from the cache the earlier attempts filled, so
        # the failing attempt starts from an empty one (the generator's own temporary store)
        with self.sessions.begin() as session:
            session.execute(delete(ResponseCacheRow))
        failing = str(self.start(plant, POST_CAP_USD)["run_id"])
        self.advance(failing)
        out["events_page_failed.json"] = self.get(self.run_path(failing, "/events?after=0"))
        out["run_list.json"] = self.get("/runs")
        out["demo_response.json"] = {
            "label": out["run_detail.json"]["label"],
            "plant": out["plant_detail.json"],
            "run": out["run_detail.json"],
            "shortlist": out["shortlist.json"],
        }
        return out


def stamp(files: dict[str, Any]) -> dict[str, Any]:
    """The only edits after generation (plan H12): every run label reads `mock`, and the
    override result reads `stored: false` (the mock echoes overrides, never stores them)."""

    def walk(value: Any) -> Any:
        if isinstance(value, dict):
            out = {k: walk(v) for k, v in value.items()}
            if set(out) == {"kind", "recorded_at", "cost_usd"} and out["kind"] == "live":
                out["kind"] = "mock"
            return out
        if isinstance(value, list):
            return [walk(v) for v in value]
        return value

    stamped = {name: walk(value) for name, value in files.items()}
    stamped["override_result.json"]["stored"] = False
    return stamped


def render(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def build_unstamped() -> dict[str, Any]:
    """The API's responses as the runs gave them, before the two mock stamps."""
    # on Windows the store's engines may still hold the file when the directory is removed
    with tempfile.TemporaryDirectory(
        prefix="guideword-fixtures-", ignore_cleanup_errors=True
    ) as work:
        generator = Generator(Path(work))
        try:
            return generator.build()
        finally:
            generator.client.close()


def generate() -> dict[str, str]:
    return render_all(stamp(build_unstamped()))


def render_all(files: dict[str, Any]) -> dict[str, str]:
    return {name: render(value) for name, value in files.items()}


def main(argv: Sequence[str] | None = None, *, out_dir: Path = FIXTURES) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="compare, write nothing")
    args = parser.parse_args(argv)
    files = generate()
    if args.check:
        stale = [
            name
            for name, text in files.items()
            if not (out_dir / name).is_file()
            or (out_dir / name).read_text(encoding="utf-8") != text
        ]
        for name in stale:
            print(f"stale: {name}")
        return 1 if stale else 0
    for name, text in files.items():
        (out_dir / name).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
