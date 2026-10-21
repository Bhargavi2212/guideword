"""`scripts/run_case.py` (spec 2.9; plan R11, R38, R43): fake transport only, no network."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import run_case

from guideword.config import Config, load_config
from guideword.gateway.fake import FakeTransport, catalog_for
from guideword.gateway.ledgers import LaptopLedger
from guideword.settings import Settings

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def config() -> Config:
    return load_config(global_budget_usd=25.0)


class Case:
    def __init__(self, tmp_path: Path, config: Config) -> None:
        self.tmp, self.config = tmp_path, config
        self.settings = Settings(
            _env_file=None,  # type: ignore[call-arg]
            database_url=f"sqlite:///{(tmp_path / 'g.db').as_posix()}",
        )
        self.ledger_path = tmp_path / "ledger.jsonl"
        self.out = tmp_path / "5b"

    def run(self, script: Any, *args: str) -> tuple[int, FakeTransport]:
        transport = FakeTransport(script, catalog_for(self.config))
        code = run_case.main(
            [str(EXAMPLE), *args],
            transport=transport,
            config=self.config,
            settings=self.settings,
            ledger=LaptopLedger(self.ledger_path),
            clock=lambda: NOW,
            out_dir=self.out,
        )
        return code, transport

    def written(self) -> dict[str, Any]:
        result: dict[str, Any] = json.loads(
            (self.out / f"{EXAMPLE.stem}.json").read_text(encoding="utf-8")
        )
        return result


@pytest.fixture
def case(tmp_path: Path, config: Config) -> Case:
    return Case(tmp_path, config)


def test_a_finished_run_prints_coverage_and_the_top_10_and_writes_the_ranked_list(
    case: Case, script: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    code, transport = case.run(script)
    out = capsys.readouterr().out
    assert code == 0 and transport.sent
    result = case.written()
    assert result["status"] == "finished"
    assert result["case"] == EXAMPLE.stem
    ranked = result["ranked"]
    assert ranked and [r["rank"] for r in ranked] == list(range(1, len(ranked) + 1))
    first = ranked[0]
    # the scorer matches the agent's own words: <cause> — <consequence> (R26c)
    assert first["text"] == "something outside — a release"
    assert {"finding_id", "question_id", "failing_component_ids", "severity_class"} <= set(first)
    assert first["frequency_assumed"] is True
    assert "finished" in out
    assert "sections" in out and "coverage" in out
    top = [line for line in out.splitlines() if line.lstrip().startswith(("1.", "10."))]
    # the printed top 10 is the folded list, one line per cause and components (R48)
    shown = len(result["folded"])
    assert len(top) == 2 if shown >= 10 else len(top) == 1
    assert "11." not in out


def test_the_report_carries_both_spend_figures_and_the_dropped_count(
    case: Case, script: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    case.run(script)
    out = capsys.readouterr().out
    result = case.written()
    assert result["spent_usd"] > 0
    # nothing cached: the analysis counter is every paid call but the post-analysis ones
    assert result["post_spent_usd"] > 0
    assert result["cap_spent_usd"] == pytest.approx(result["spent_usd"] - result["post_spent_usd"])
    assert result["dropped"] == {"total": 0, "distinct": 0}
    # the run's duration, from its first and last event (the fake clock stands still)
    assert result["seconds"] == 0.0
    assert "dropped 0" in out
    assert "paid $" in out


def test_a_run_at_the_severity_reserve_names_the_cap_and_what_was_left(
    case: Case, capped_script: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """R38: the orchestrator stops at the cap minus the reserve, severity still runs, and the
    run ends stopped_cap with questions open; the output says so."""
    code, _ = case.run(capped_script, "--cap", "0.08")
    out = capsys.readouterr().out
    result = case.written()
    assert result["status"] == "stopped_cap"
    assert code == 0
    assert "severity reserve" in [hit["reason"] for hit in result["cap_hits"]]
    assert result["open_questions"] > 0
    assert f"{result['open_questions']} questions left open" in out
    assert f"{result['unrated']} findings unrated" in out
    assert "stopped_cap" in out


def test_a_second_run_of_the_same_case_is_served_from_the_cache(
    case: Case, script: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    case.run(script)
    first = case.written()
    _, transport = case.run(script)
    assert transport.sent == []
    assert case.written()["ranked"] == first["ranked"]


def test_the_cap_defaults_to_caps_yaml_and_use_goes_on_the_ledger(
    case: Case, script: Any, config: Config
) -> None:
    case.run(script, "--use", "test_5")
    assert case.written()["spend_cap_usd"] == config.caps.run.run_spend_cap_usd
    lines = [json.loads(x) for x in case.ledger_path.read_text(encoding="utf-8").splitlines()]
    assert lines and {line["use"] for line in lines} == {"test_5"}


def test_an_invalid_plant_file_is_refused_without_a_call(
    case: Case, script: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    bad["equipment"][0]["location_id"] = "NOWHERE"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    transport = FakeTransport(script, catalog_for(case.config))
    code = run_case.main(
        [str(path)],
        transport=transport,
        config=case.config,
        settings=case.settings,
        ledger=LaptopLedger(case.ledger_path),
        clock=lambda: NOW,
        out_dir=case.out,
    )
    assert code == 1
    assert transport.sent == []
    assert "NOWHERE" in capsys.readouterr().err


def test_not_credible_is_counted_apart_from_answered(
    case: Case, capsys: pytest.CaptureFixture[str], script_factory: Any
) -> None:
    """Coverage counts not credible as checked; the summary shows how many were dismissed, so a
    checked count never hides them."""
    case.run(script_factory(not_credible_every=3))
    out = capsys.readouterr().out
    result = case.written()
    by_list = {line["list"]: line for line in result["not_credible"]}
    total = sum(line["not_credible"] for line in result["not_credible"])
    assert total > 0
    assert (
        by_list["matrix"]["answered"] + by_list["matrix"]["not_credible"]
        <= by_list["matrix"]["checked"]
    )
    assert f"not credible {total}" in out


def test_the_report_folds_repeated_causes_and_prints_the_folded_top_10(
    case: Case, script: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """R48: the fake script gives every question the same cause on the first location, so many
    findings share a cause and components; the folded list shows each once."""
    case.run(script)
    out = capsys.readouterr().out
    result = case.written()
    folded, ranked = result["folded"], result["ranked"]
    assert 0 < len(folded) < len(ranked)
    assert sum(1 + line["folded_count"] for line in folded) == len(ranked)
    assert [line["rank"] for line in folded] == list(range(1, len(folded) + 1))
    first = folded[0]
    assert first["finding_id"] == ranked[0]["finding_id"]
    assert len(first["folded_finding_ids"]) == first["folded_count"]
    assert f"(+{first['folded_count']} folded)" in out


def test_case_d_at_1_20_on_the_fake_gateway_defers_then_sends_then_stops_for_a_real_reason(
    tmp_path: Path, script_factory: Any
) -> None:
    """The $0 check before the live case D run (R13 as amended): prices ×3 and answers billed at
    their estimated input and near max_tokens, so dispatches near the end defer batches; each
    deferred question is sent at bulk by a later dispatch (never promoted, never a repeat), and
    the run ends for a stated reason within its cap."""
    import sqlite3  # noqa: PLC0415

    base = load_config(global_budget_usd=25.0)
    tiers = {
        tier: model.model_copy(
            update={
                "input_usd_per_1m": model.input_usd_per_1m * 3,
                "output_usd_per_1m": model.output_usd_per_1m * 3,
            }
        )
        for tier, model in base.models.tiers.items()
    }
    config = base.model_copy(update={"models": base.models.model_copy(update={"tiers": tiers})})
    script = script_factory(orchestrator_output_tokens=4000, specialist_tokens=(None, 12_000))
    transport = FakeTransport(script, catalog_for(config))
    case_d = REPO / "cases" / "dev" / "case_d.json"
    run_case.main(
        [str(case_d), "--cap", "1.20"],
        transport=transport,
        config=config,
        settings=Settings(
            _env_file=None,  # type: ignore[call-arg]
            database_url=f"sqlite:///{(tmp_path / 'g.db').as_posix()}",
        ),
        ledger=LaptopLedger(tmp_path / "l.jsonl"),
        clock=lambda: NOW,
        out_dir=tmp_path / "5b",
    )
    report = json.loads((tmp_path / "5b" / "case_d.json").read_text(encoding="utf-8"))
    dispatches = []
    with sqlite3.connect(tmp_path / "g.db") as db:
        for (record,) in db.execute("select record from events order by seq"):
            event = json.loads(record)
            if event["type"] == "dispatch":
                dispatches.append(event["payload"])
    deferring = [i for i, d in enumerate(dispatches) if d["deferred_at_admission"]]
    assert deferring, "no dispatch deferred a batch"
    first = deferring[0]
    deferred = {q for d in dispatches[first]["deferred_at_admission"] for q in d["question_ids"]}
    later = {q for d in dispatches[first + 1 :] for q in d["question_ids"]}
    assert deferred & later, "the deferred questions were not dispatched again"
    sent_at_bulk = {
        q["id"]
        for job, request in transport.sent
        if job == "specialist_bulk"
        for q in json.loads(
            re.search(
                r"<questions>\s*(.*?)\s*</questions>", request["messages"][0]["content"], re.S
            ).group(1)  # type: ignore[union-attr]
        )
    }
    resent = deferred & later
    assert resent <= sent_at_bulk  # sent at their own level, not promoted
    assert report["cap_spent_usd"] <= 1.20
    assert report["status"] in ("finished", "stopped_cap")
    reasons = [hit["reason"] for hit in report["cap_hits"]]
    assert set(reasons) <= {"severity reserve", "admission", "questions left open"}
    if report["status"] == "stopped_cap":
        assert reasons and report["open_questions"] > 0


def test_with_no_hypotheses_5b_from_hybrid_equals_the_current_ranking(
    case: Case, script: Any
) -> None:
    case.run(script)
    result = case.written()
    assert result["hypotheses"] == []
    assert result["5b-from-hybrid"] == result["folded"]
    assert {line["tier"] for line in result["hybrid"]} == {"also_found"}
    assert [line["finding_id"] for line in result["hybrid"]] == [
        line["finding_id"] for line in result["folded"]
    ]


def test_a_supported_screen_hypothesis_heads_the_list_as_confirmed(
    case: Case, script_factory: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """The fake specialists answer every question with an outside-library external cause on the
    first location of their context; a screen hypothesis of that shape is confirmed."""
    plant = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    location = plant["locations"][0]["id"]
    screen = [
        {
            "rank": 1,
            "mechanism": "something outside hits the building",
            "component_ids": [location],
            "chemical_ids": [],
            "failing_component_type": "external",
            "cause_id": "outside_library",
            "cause_text": "something outside",
            "consequence": "a release in the building",
            "reason": "test",
        }
    ]
    case.run(script_factory(screen_hypotheses=screen))
    out = capsys.readouterr().out
    result = case.written()
    first = result["hybrid"][0]
    assert first["tier"] == "confirmed" and first["hypothesis_rank"] == 1
    assert first["text"] == "something outside hits the building — a release in the building"
    assert first["support_finding_ids"]
    assert result["5a-plant"][0]["text"] == first["text"]
    assert "confirmed" in out


def test_case_d_end_to_end_on_the_fake_gateway_with_a_scripted_screen(
    tmp_path: Path, config: Config, script_factory: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """The $0 check before the G2b runs (R50): plant_screen → analysis → severity → ranked on
    case D's plant file, with priority dispatch. The scripted screen is generic, built from
    the plant file's own lists (every location; the first pump), and encodes no cause of
    case D: one hypothesis matches what the fake specialists find, one does not."""
    case_d = REPO / "cases" / "dev" / "case_d.json"
    plant = json.loads(case_d.read_text(encoding="utf-8"))
    pump = next(e["id"] for e in plant["equipment"] if e["type"] == "pump")
    screen = [
        {
            "rank": 1,
            "mechanism": "something outside hits the plant",
            "component_ids": [loc["id"] for loc in plant["locations"]],
            "chemical_ids": [],
            "failing_component_type": "external",
            "cause_id": "outside_library",
            "cause_text": "something outside",
            "consequence": "a release",
            "reason": "test",
        },
        {
            "rank": 2,
            "mechanism": "a pump stops",
            "component_ids": [pump],
            "chemical_ids": [],
            "failing_component_type": "pump",
            "cause_id": "outside_library",
            "cause_text": "a pump stops",
            "consequence": "a loss of flow",
            "reason": "test",
        },
    ]
    transport = FakeTransport(
        script_factory(screen_hypotheses=screen, priority=True), catalog_for(config)
    )
    code = run_case.main(
        [str(case_d), "--cap", "1.20"],
        transport=transport,
        config=config,
        settings=Settings(
            _env_file=None,  # type: ignore[call-arg]
            database_url=f"sqlite:///{(tmp_path / 'g.db').as_posix()}",
        ),
        ledger=LaptopLedger(tmp_path / "l.jsonl"),
        clock=lambda: NOW,
        out_dir=tmp_path / "5b",
    )
    out = capsys.readouterr().out
    report = json.loads((tmp_path / "5b" / "case_d.json").read_text(encoding="utf-8"))
    assert code == 0 and report["status"] == "finished"
    assert report["cap_spent_usd"] <= 1.20 and report["open_questions"] == 0
    assert [job for job, _ in transport.sent][0] == "plant_screen"
    assert [h["rank"] for h in report["hypotheses"]] == [1, 2]
    pump_hypothesis = report["hypotheses"][1]
    assert pump_hypothesis["question_ids"], "the pump hypothesis links no question"
    tiers = [line["tier"] for line in report["hybrid"]]
    assert tiers[0] == "confirmed" and tiers[-1] == "unconfirmed"
    # every fake finding is the outside cause on a location, so all support rank 1
    order = ["confirmed", "also_found", "unconfirmed"]
    assert tiers == sorted(tiers, key=order.index)
    assert len(report["hybrid"][0]["support_finding_ids"]) == len(report["ranked"])
    assert report["hybrid"][-1]["flag"] == "not confirmed by the checks — engineer to review"
    assert [line["rank"] for line in report["5a-plant"]] == [1, 2]
    assert report["5b-from-hybrid"] == report["folded"]
    priority = report["priority"]
    assert priority["linked_questions"] == len(pump_hypothesis["question_ids"])
    # acceptance (R50 review): the linked questions are answered before, or with, the first
    # dispatch that sends an unlinked one, and that dispatch leads with them
    linked = pump_hypothesis["question_ids"]
    assert priority["linked_answered_before_first_unlinked"] == len(linked) > 0
    import sqlite3  # noqa: PLC0415

    with sqlite3.connect(tmp_path / "g.db") as db:
        dispatches = [
            json.loads(record)["payload"]
            for (record,) in db.execute("select record from events order by seq")
            if json.loads(record)["type"] == "dispatch"
        ]
    first = dispatches[0]
    assert first["priority"] is True and first["selected_by_code"] is True
    assert first["question_ids"][: len(linked)] == sorted(linked)
    assert first["linked_answered"] == len(linked)
    assert "before the first unlinked dispatch" in out and "[confirmed #1]" in out
