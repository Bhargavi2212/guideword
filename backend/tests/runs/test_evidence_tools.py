"""The evidence step's tools (Phase 4 plan PR 5b): an injected precedent index is used as
given, so a fake run never reads the real index (CLAUDE.md section 5)."""

from datetime import UTC, datetime
from pathlib import Path

from guideword.config import load_config
from guideword.gateway.cache import ResponseCache
from guideword.gateway.ledgers import LaptopLedger
from guideword.reference.precedents import PrecedentIndex, PrecedentRow
from guideword.runs.case import evidence_tools
from guideword.runs.db import make_session_factory
from guideword.schema.enums import BudgetUse
from guideword.tools.web import FakeSearch

T = datetime(2026, 10, 23, tzinfo=UTC)


def test_an_injected_precedent_index_is_used_as_given(tmp_path: Path) -> None:
    row = PrecedentRow(
        id="MP-0001",
        title="Mock precedent",
        url="https://precedent.mock/MP-0001",
        source="synthetic test row",
    )
    index = PrecedentIndex((row,), "synthetic")
    tools = evidence_tools(
        config=load_config(global_budget_usd=25.0),
        cache=ResponseCache(make_session_factory(f"sqlite:///{(tmp_path / 'g.db').as_posix()}")),
        ledger=LaptopLedger(tmp_path / "l.jsonl"),
        use=BudgetUse.DEVELOPMENT,
        phase="5",
        clock=lambda: T,
        search=FakeSearch(lambda q, n: {"results": []}),
        index=index,
    )
    assert tools.index is index
