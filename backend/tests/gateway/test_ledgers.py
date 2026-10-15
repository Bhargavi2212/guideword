"""The laptop and hosted ledgers (PROJECT.md §7; plan R16)."""

from datetime import UTC, datetime
from pathlib import Path

import budget_status
import live_call
import pytest

from guideword.gateway.estimate import cost_usd, estimate_cost
from guideword.gateway.ledgers import HostedLedger, LaptopLedger, ledger_for
from guideword.runs.db import make_session_factory
from guideword.schema.enums import BudgetUse, Environment
from guideword.schema.records import SpendEntry
from guideword.settings import Settings

T = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


def _entry(
    environment: Environment, use: BudgetUse, cost: float, purpose: str = "job"
) -> SpendEntry:
    return SpendEntry(
        ts=T,
        kind="model",
        environment=environment,
        phase="2",
        use=use,
        model="m",
        input_tokens=1,
        output_tokens=1,
        cost_usd=cost,
        script="gateway",
        purpose=purpose,
    )


@pytest.fixture
def hosted(tmp_path: Path) -> HostedLedger:
    return HostedLedger(make_session_factory(f"sqlite:///{(tmp_path / 'g.db').as_posix()}"))


def test_laptop_ledger_appends_and_sums_by_phase_and_use(tmp_path: Path) -> None:
    ledger = LaptopLedger(tmp_path / "ledger.jsonl")
    ledger.append(_entry(Environment.LAPTOP, BudgetUse.DEVELOPMENT, 0.25))
    ledger.append(_entry(Environment.LAPTOP, BudgetUse.TEST_5, 0.5))
    assert ledger.spent() == pytest.approx(0.75)
    assert ledger.spent(use=BudgetUse.TEST_5) == pytest.approx(0.5)
    assert ledger.spent(phase="2") == pytest.approx(0.75)
    assert ledger.spent(phase="0") == 0


def test_hosted_ledger_appends_and_sums(hosted: HostedLedger) -> None:
    hosted.append(_entry(Environment.HOSTED, BudgetUse.JUDGING, 0.25, "a"))
    hosted.append(_entry(Environment.HOSTED, BudgetUse.JUDGING, 0.25, "b"))
    assert hosted.spent(use=BudgetUse.JUDGING) == pytest.approx(0.5)
    assert len(hosted.entries()) == 2


def test_laptop_and_hosted_ledgers_never_read_each_other(
    tmp_path: Path, hosted: HostedLedger
) -> None:
    laptop = LaptopLedger(tmp_path / "ledger.jsonl")
    laptop.append(_entry(Environment.LAPTOP, BudgetUse.DEVELOPMENT, 1.0))
    hosted.append(_entry(Environment.HOSTED, BudgetUse.JUDGING, 2.0))
    assert laptop.spent() == pytest.approx(1.0)
    assert hosted.spent() == pytest.approx(2.0)
    with pytest.raises(ValueError):
        laptop.append(_entry(Environment.HOSTED, BudgetUse.JUDGING, 1.0))
    with pytest.raises(ValueError):
        hosted.append(_entry(Environment.LAPTOP, BudgetUse.DEVELOPMENT, 1.0))


def test_ledger_for_follows_the_environment_setting(tmp_path: Path) -> None:
    sessions = make_session_factory(f"sqlite:///{(tmp_path / 'g.db').as_posix()}")
    laptop = ledger_for(
        Settings(_env_file=None, guideword_env="laptop"), sessions, tmp_path / "l.jsonl"
    )
    hosted = ledger_for(Settings(_env_file=None, guideword_env="hosted"), sessions)
    assert isinstance(laptop, LaptopLedger)
    assert isinstance(hosted, HostedLedger)


def test_live_call_and_budget_status_use_the_moved_ledger() -> None:
    """R16: one ledger class and one estimate rule, re-exported from scripts/live_call.py."""
    assert live_call.Ledger is LaptopLedger
    assert budget_status.Ledger is LaptopLedger
    assert live_call.estimate_cost is estimate_cost
    assert live_call.cost_usd is cost_usd
