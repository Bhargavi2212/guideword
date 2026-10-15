"""scripts/gateway_check.py with a fake transport: never the network, never a key."""

from pathlib import Path
from typing import Any

import gateway_check
import pytest

from guideword.config import Config, load_config
from guideword.gateway.fake import FakeTransport, catalog_for, reply
from guideword.gateway.ledgers import LaptopLedger
from guideword.gateway.transport import ToolCallRequest
from guideword.schema.enums import BudgetUse
from guideword.settings import Settings


@pytest.fixture(scope="module")
def config() -> Config:
    return load_config(global_budget_usd=25.0)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, database_url=f"sqlite:///{(tmp_path / 'g.db').as_posix()}")


def _script(tools_work: bool) -> Any:
    def script(job: str, request: dict[str, Any]) -> Any:
        if request.get("tools") and not any(m.get("role") == "tool" for m in request["messages"]):
            if not tools_work:
                return reply("I cannot call tools here.")
            return reply(tool_calls=(ToolCallRequest("c1", "lookup_unit", '{"name": "pressure"}'),))
        return reply({"verdict": "yes", "reason": "kPa gauge"})

    return script


def _run(config: Config, settings: Settings, tmp_path: Path, tools_work: bool) -> FakeTransport:
    transport = FakeTransport(_script(tools_work), catalog_for(config))
    status = gateway_check.main(
        [],
        transport=transport,
        config=config,
        settings=settings,
        ledger=LaptopLedger(tmp_path / "ledger.jsonl"),
        out=tmp_path / "gateway-check.md",
    )
    assert status == 0
    return transport


def test_check_writes_the_results_file(config: Config, settings: Settings, tmp_path: Path) -> None:
    transport = _run(config, settings, tmp_path, tools_work=True)
    text = (tmp_path / "gateway-check.md").read_text(encoding="utf-8")
    assert "Tools with schema on Lightning:** works" in text
    assert text.count("| schema |") == 4
    # 4 tier calls + the tool call + the answer after the tool result
    assert len(transport.sent) == 6


def test_check_reports_when_tools_and_schema_do_not_combine(
    config: Config, settings: Settings, tmp_path: Path
) -> None:
    _run(config, settings, tmp_path, tools_work=False)
    assert "does not work" in (tmp_path / "gateway-check.md").read_text(encoding="utf-8")


def test_check_uses_development_and_phase_2(
    config: Config, settings: Settings, tmp_path: Path
) -> None:
    _run(config, settings, tmp_path, tools_work=True)
    entries = LaptopLedger(tmp_path / "ledger.jsonl").entries()
    assert entries
    assert {(e.use, e.phase) for e in entries} == {(BudgetUse.DEVELOPMENT, "2")}
