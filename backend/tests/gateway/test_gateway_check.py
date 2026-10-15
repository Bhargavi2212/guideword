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

TOOL_CALL = ToolCallRequest("c1", "lookup_unit", '{"name": "pressure"}')


@pytest.fixture(scope="module")
def config() -> Config:
    return load_config(global_budget_usd=25.0)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, database_url=f"sqlite:///{(tmp_path / 'g.db').as_posix()}")


def _script(combined_calls_tool: bool) -> Any:
    """Like the live run of 2026-10-15: with a strict schema present, Lightning answers in the
    schema instead of calling the tool; with tools alone, it calls the tool."""

    def script(job: str, request: dict[str, Any]) -> Any:
        after_tool = any(m.get("role") == "tool" for m in request["messages"])
        if request.get("tools") and not after_tool:
            if "response_format" in request and not combined_calls_tool:
                return reply({"verdict": "rejected", "reason": "unknown"})
            return reply(tool_calls=(TOOL_CALL,))
        return reply({"verdict": "yes", "reason": "kPa gauge"})

    return script


def _run(
    config: Config, settings: Settings, tmp_path: Path, combined_calls_tool: bool
) -> tuple[FakeTransport, str]:
    transport = FakeTransport(_script(combined_calls_tool), catalog_for(config))
    status = gateway_check.main(
        [],
        transport=transport,
        config=config,
        settings=settings,
        ledger=LaptopLedger(tmp_path / "ledger.jsonl"),
        out=tmp_path / "gateway-check.md",
    )
    assert status == 0
    return transport, (tmp_path / "gateway-check.md").read_text(encoding="utf-8")


def test_both_paths_working(config: Config, settings: Settings, tmp_path: Path) -> None:
    transport, text = _run(config, settings, tmp_path, combined_calls_tool=True)
    assert "Tools with schema on Lightning:** works" in text
    assert "Two calls on Lightning (tool, then the schema answer):** works" in text
    assert text.count("| schema |") == 4
    # 4 tier calls, 2 for tools with schema, 2 for the two-call path
    assert len(transport.sent) == 8


def test_combined_fails_and_two_calls_work(
    config: Config, settings: Settings, tmp_path: Path
) -> None:
    """The live result of 2026-10-15."""
    transport, text = _run(config, settings, tmp_path, combined_calls_tool=False)
    assert "Tools with schema on Lightning:** does not work" in text
    assert "Two calls on Lightning (tool, then the schema answer):** works" in text
    assert "no tool call" in text
    assert len(transport.sent) == 7


def test_the_two_call_path_sends_no_schema_with_the_tools(
    config: Config, settings: Settings, tmp_path: Path
) -> None:
    transport, _ = _run(config, settings, tmp_path, combined_calls_tool=False)
    tool_only = [r for _, r in transport.sent if r.get("tools") and "response_format" not in r]
    assert len(tool_only) == 1


def test_a_rerun_is_served_from_the_cache(
    config: Config, settings: Settings, tmp_path: Path
) -> None:
    _run(config, settings, tmp_path, combined_calls_tool=False)
    transport, text = _run(config, settings, tmp_path, combined_calls_tool=False)
    assert transport.sent == []
    assert "Paid this run:** $0.00000" in text
    assert "| no |" not in text


def test_check_uses_development_and_phase_2(
    config: Config, settings: Settings, tmp_path: Path
) -> None:
    _run(config, settings, tmp_path, combined_calls_tool=True)
    entries = LaptopLedger(tmp_path / "ledger.jsonl").entries()
    assert entries
    assert {(e.use, e.phase) for e in entries} == {(BudgetUse.DEVELOPMENT, "2")}
