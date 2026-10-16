"""`scripts/run_case.py` (spec 2.9; plan R11, R38, R43): fake transport only, no network."""

import json
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
    assert len(top) == 2 if len(ranked) >= 10 else len(top) == 1
    assert "11." not in out


def test_the_report_carries_both_spend_figures_and_the_dropped_count(
    case: Case, script: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    case.run(script)
    out = capsys.readouterr().out
    result = case.written()
    assert result["spent_usd"] > 0
    assert result["cap_spent_usd"] == pytest.approx(result["spent_usd"])
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
    code, _ = case.run(capped_script, "--cap", "0.17")
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
