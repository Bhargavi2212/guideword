"""The generated contract fixtures (Phase 5 plan B1, C5, G3, Q2, H9, H12, H13).

The fixtures come from $0 fake runs of Mock Plant A through the real API
(`scripts/make_fixtures.py`). One generation serves every test here.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

import make_fixtures
import pytest

from guideword.api import models as api
from guideword.schema.events import SCHEMA_V1_9

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "contract" / "fixtures"
# the real stores this must never touch (git-ignored; absent in CI)
REAL = [REPO / "budget" / "ledger.jsonl", REPO / "guideword.db"]


def _hash(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


@pytest.fixture(scope="module")
def generated() -> tuple[dict[str, Any], dict[str, Any], dict[Path, str | None]]:
    before = {path: _hash(path) for path in REAL}
    unstamped = make_fixtures.build_unstamped()
    return unstamped, make_fixtures.stamp(unstamped), before


def _committed(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_regenerating_the_fixtures_gives_the_same_files(generated: Any) -> None:
    _, stamped, _ = generated
    rendered = make_fixtures.render_all(stamped)
    stale = [n for n, text in rendered.items() if (FIXTURES / n).read_text("utf-8") != text]
    assert stale == [], "run: python scripts/make_fixtures.py"


def test_making_fixtures_leaves_the_real_ledger_and_store_untouched(generated: Any) -> None:
    _, _, before = generated
    assert {path: _hash(path) for path in REAL} == before


def test_only_the_two_mock_stamps_differ_from_the_api_output(generated: Any) -> None:
    unstamped, stamped, _ = generated
    differences: list[str] = []

    def walk(a: Any, b: Any, where: str) -> None:
        if isinstance(a, dict) and isinstance(b, dict):
            assert set(a) == set(b), where
            for key in a:
                walk(a[key], b[key], f"{where}.{key}")
        elif isinstance(a, list) and isinstance(b, list):
            assert len(a) == len(b), where
            for i, (x, y) in enumerate(zip(a, b, strict=True)):
                walk(x, y, f"{where}[{i}]")
        elif a != b:
            differences.append(f"{where}: {a!r} -> {b!r}")

    for name in unstamped:
        walk(unstamped[name], stamped[name], name)
    assert differences
    for line in differences:
        assert line.endswith(".kind: 'live' -> 'mock'") or line == (
            "override_result.json.stored: True -> False"
        ), line


def test_run_fixtures_agree_with_the_plant_fixtures() -> None:
    plant = _committed("plant_detail.json")
    sections = [s["id"] for s in plant["sections"]]
    run = _committed("run_detail.json")["run"]
    assert run["plant_record_id"] == plant["plant_record_id"]
    assert run["section_snapshot"] == sections
    assert [s["id"] for s in _committed("run_sections.json")["sections"]] == sections
    assert _committed("plant_list.json")["plants"][0]["plant_record_id"] == plant["plant_record_id"]


def test_every_generated_event_carries_the_v1_9_stamp_and_is_valid() -> None:
    for name in ("events_page.json", "events_page_failed.json"):
        events = _committed(name)["events"]
        assert events, name
        for event in events:
            assert event["payload_schema"] == SCHEMA_V1_9, (name, event["seq"])
            assert event["payload_invalid"] is False, (name, event["seq"])
    assert all(e["payload_schema"] == SCHEMA_V1_9 for e in _committed("run_dump.json")["events"])


def test_the_generated_run_covers_every_case_in_table_f() -> None:
    """The cases the hand-built fixtures showed (plan table F), plus those the plan added."""
    dump = api.RunDump.model_validate(_committed("run_dump.json"))
    questions = {q.id: q for q in dump.questions}
    # question kinds, statuses, and the open engineer question
    assert {q.kind for q in dump.questions} >= {
        "matrix",
        "chemical_pair",
        "chemical_environment",
        "procedure_step",
        "relief_discharge",
        "planned_work",
    }
    assert questions["m:S-MX-1:more:pressure"].status == "not_credible"
    assert questions["m:S-MX-1:more:pressure"].not_credible_reason
    assert questions["work:W-1:PSV-1"].status == "failed"
    created = api.QuestionCreated.model_validate(_committed("question_created.json")).question
    assert created.id.startswith("eng:") and created.status == "open"
    # findings: tiers, library and outside-library causes, adequacy, confidence, severities
    findings = dump.findings
    assert {f.tier for f in findings} == {"lightning", "ultra"}
    assert {f.cause_id for f in findings} >= {"C01", "C14", "C20", "outside_library"}
    assert {f.adequacy for f in findings} == {"adequate", "inadequate", "unknown"}
    assert {f.confidence for f in findings} == {"sure", "unsure"}
    assert {f.severity_class for f in findings} == {"S2", "S3", "S4"}
    assert any(not f.safeguard_ids for f in findings)
    # hypotheses: one with questions, one without, one dropped
    assert any(h.question_ids for h in dump.hypotheses)
    assert any(not h.question_ids for h in dump.hypotheses)
    types = {e.type for e in dump.events}
    assert {"hypothesis_added", "hypothesis_dropped"} <= types
    # a chain, LOPA of each kind, a recommendation
    assert len(dump.chains) == 1 and len(dump.chains[0].links) == 2
    lopa = dump.lopa_records
    layers = [layer for r in lopa for layer in r.layers]
    assert any(layer.credited for layer in layers)
    assert any(layer.reason == "not argued — no credit" for layer in layers)
    assert any(not r.complete and r.missing_fact_ids == ["L-12.length_m"] for r in lopa)
    assert any(r.complete and not r.layers for r in lopa) or any(
        r.target_id.startswith("ch:") for r in lopa
    )
    assert dump.recommendations
    # evidence: each kind and verdict
    evidence = {(e.kind, e.verdict) for e in dump.evidence}
    assert {("calculation", "confirmed"), ("calculation", "none")} <= evidence
    assert {("precedent", "confirmed"), ("precedent", "none")} <= evidence
    # the cap stop and its resume, a stored override, the tiers on calls and dispatches
    assert {"cap_hit", "run_extended"} <= types
    resumed = [e for e in dump.events if e.type == "run_extended"]
    assert any(e.payload["resumed_after_post_cap"] for e in resumed)
    assert [h.payload["cap"] for h in dump.events if h.type == "cap_hit"] == ["post"]
    assert dump.overrides and dump.overrides[0].action == "change_severity"
    assert all(e.payload["tier"] for e in dump.events if e.type in ("model_call", "dispatch"))
    # the cancelled and failed attempts
    assert _committed("run_status_result.json")["status"] == "cancelled"
    failed = {e["type"] for e in _committed("events_page_failed.json")["events"]}
    assert "run_failed" in failed
    # coverage shows empty lists, an unsure count and a failed question
    coverage = api.Coverage.model_validate(_committed("coverage.json"))
    assert any(line.total == 0 for line in coverage.lists)
    assert any(line.unsure for line in coverage.lists)
    assert coverage.failed_question_ids == ["work:W-1:PSV-1"]
    # the worksheet shows the override state
    rows = api.Worksheet.model_validate(_committed("worksheet.json")).rows
    assert any(row.override_state != "none" for row in rows)
