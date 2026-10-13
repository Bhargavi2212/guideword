"""scripts/budget_status.py (spec 0.3): limits come from settings and caps.yaml, never literals."""

import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

import budget_status
import pytest

from guideword.config import load_config
from guideword.schema.enums import BudgetUse, Environment
from guideword.schema.records import SpendEntry

CONFIG = Path(__file__).resolve().parents[2] / "config"
TS = datetime(2026, 10, 13, 18, 0, tzinfo=UTC)


def _entry(kind: str, cost: float, **fields: object) -> SpendEntry:
    data: dict[str, object] = {
        "ts": TS,
        "kind": kind,
        "environment": Environment.LAPTOP,
        "phase": "0",
        "use": BudgetUse.DEVELOPMENT,
        "cost_usd": cost,
        "script": "live_call.py",
        "purpose": "test",
    }
    data.update(fields)
    return SpendEntry.model_validate(data)


OPENING = _entry("opening_balance", 1.20, phase="opening_balance")
ULTRA = _entry(
    "model", 0.10, model="nvidia/Nemotron-3-Ultra-550b-a55b", input_tokens=10, output_tokens=5
)
LIGHT = _entry(
    "model", 0.02, model="nvidia/Nemotron-3_5-Lightning", input_tokens=10, output_tokens=5
)
SEARCH = _entry("tavily", 0.0, searches=1)


def test_refuses_remaining_without_an_opening_balance() -> None:
    report = budget_status.build_report([ULTRA, SEARCH], load_config(global_budget_usd=25.0), 25.0)
    assert "opening balance" in report.lower()
    assert "remaining" not in report.lower().replace("remaining: refused", "")


def test_report_with_opening_balance() -> None:
    report = budget_status.build_report(
        [OPENING, ULTRA, LIGHT, SEARCH], load_config(global_budget_usd=25.0), 25.0
    )
    assert "nvidia/Nemotron-3-Ultra-550b-a55b" in report
    assert "Tavily searches: 1" in report
    assert re.search(r"laptop spent:\s+\$1\.32", report)
    assert re.search(r"laptop remaining:\s+\$17\.68 of \$19\.00", report)
    assert re.search(r"development\s+spent \$1\.32\s+remaining \$3\.68 of \$5\.00", report)
    assert "GLOBAL_BUDGET_USD: $25.00" in report
    assert "reconcile" in report.lower()


def test_limits_come_from_caps_and_settings(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    shutil.copytree(CONFIG, config_dir)
    caps = config_dir / "caps.yaml"
    text = caps.read_text(encoding="utf-8")
    text = text.replace(
        "development: {environment: laptop, allowance_usd: 5.00}",
        "development: {environment: laptop, allowance_usd: 10.00}",
    )
    text = text.replace("laptop: {allowance_usd: 19.00}", "laptop: {allowance_usd: 24.00}")
    caps.write_text(text, encoding="utf-8", newline="\n")
    config = load_config(config_dir, global_budget_usd=30.0)
    report = budget_status.build_report([OPENING], config, 30.0)
    assert re.search(r"laptop remaining:\s+\$22\.80 of \$24\.00", report)
    assert "GLOBAL_BUDGET_USD: $30.00" in report


def test_spend_by_phase() -> None:
    report = budget_status.build_report(
        [OPENING, ULTRA, LIGHT], load_config(global_budget_usd=25.0), 25.0
    )
    assert re.search(r"phase 0:\s+\$0\.12", report)


def test_no_budget_literals_in_script() -> None:
    source = Path(budget_status.__file__).read_text(encoding="utf-8")
    for literal in ("19", "25", "6.00", "0.65"):
        assert re.search(rf"(?<![\w.]){re.escape(literal)}(?![\w.])", source) is None, literal


@pytest.mark.parametrize("missing", [[], [SEARCH]])
def test_empty_or_search_only_ledger(missing: list[SpendEntry]) -> None:
    report = budget_status.build_report(missing, load_config(global_budget_usd=25.0), 25.0)
    assert "opening balance" in report.lower()
