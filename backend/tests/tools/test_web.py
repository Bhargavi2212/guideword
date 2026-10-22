"""Tavily inside `guideword/tools` (Phase 4 spec 4.3 rules; plan PR 5a, Q14, G6, G18).

A fake search client only: no network, and no Tavily result is ever read by Claude Code.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import Session, sessionmaker

from guideword.config import Config, load_config
from guideword.gateway.cache import ResponseCache
from guideword.gateway.client import BudgetRefused
from guideword.gateway.ledgers import HostedLedger, LaptopLedger, Ledger
from guideword.gateway.replay import ReplayMiss
from guideword.runs.db import make_session_factory
from guideword.schema.enums import BudgetUse, Environment, RunStatus
from guideword.tools.web import (
    FakeSearch,
    ReplaySearch,
    SearchFailed,
    WebSearch,
    search_cache_key,
)

NOW = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)
HITS = {
    "results": [
        {"title": "Mock reboiler rupture", "url": "https://mock.invalid/a", "content": "A shell"},
        {"title": "No URL here", "content": "dropped"},
        {"title": "Mock mixer fire", "url": "https://mock.invalid/b", "content": "A mixer"},
    ]
}


@pytest.fixture(scope="module")
def config() -> Config:
    return load_config(global_budget_usd=25.0)


@pytest.fixture
def sessions(tmp_path: Path) -> sessionmaker[Session]:
    return make_session_factory(f"sqlite:///{(tmp_path / 'w.db').as_posix()}")


def _web(
    config: Config,
    sessions: sessionmaker[Session],
    ledger: Ledger,
    client: Any,
    *,
    use: BudgetUse = BudgetUse.DEVELOPMENT,
    phase: str = "4",
) -> WebSearch:
    return WebSearch(
        client=client,
        cache=ResponseCache(sessions),
        ledger=ledger,
        config=config,
        use=use,
        phase=phase,
        clock=lambda: NOW,
    )


def test_a_search_writes_one_tavily_ledger_line(
    config: Config, sessions: sessionmaker[Session], tmp_path: Path
) -> None:
    ledger = LaptopLedger(tmp_path / "ledger.jsonl")
    client = FakeSearch(lambda query, n: HITS)
    result = _web(config, sessions, ledger, client).search("reboiler isolated heating", 5)
    assert [h.url for h in result.hits] == ["https://mock.invalid/a", "https://mock.invalid/b"]
    assert not result.cache_hit
    assert client.sent == [("reboiler isolated heating", 5)]
    (entry,) = ledger.entries()
    assert (entry.kind, entry.searches, entry.cost_usd) == ("tavily", 1, 0.0)
    assert (entry.phase, entry.use, entry.environment) == ("4", "development", "laptop")
    assert "reboiler" not in entry.purpose  # the query is data; the ledger names the job


def test_a_repeated_search_is_served_from_the_cache_with_no_ledger_line(
    config: Config, sessions: sessionmaker[Session], tmp_path: Path
) -> None:
    ledger = LaptopLedger(tmp_path / "ledger.jsonl")
    client = FakeSearch(lambda query, n: HITS)
    web = _web(config, sessions, ledger, client)
    first = web.search("q", 5)
    second = web.search("q", 5)
    assert second.cache_hit and second.hits == first.hits
    assert second.cache_key == first.cache_key == search_cache_key("q", 5)
    assert len(client.sent) == 1
    assert len(ledger.entries()) == 1
    # another max_results is another search
    web.search("q", 3)
    assert len(client.sent) == 2


def test_tavily_spend_is_written_to_the_laptop_and_hosted_ledgers(
    config: Config, sessions: sessionmaker[Session], tmp_path: Path
) -> None:
    """Q14: the run environment's ledger, laptop or hosted, through the same path."""
    hosted = HostedLedger(sessions)
    web = _web(config, sessions, hosted, FakeSearch(lambda q, n: HITS), use=BudgetUse.JUDGING)
    web.search("q", 5)
    (entry,) = hosted.entries()
    assert (entry.kind, entry.environment) == ("tavily", Environment.HOSTED)


def test_a_search_under_another_environments_use_is_refused_before_sending(
    config: Config, sessions: sessionmaker[Session], tmp_path: Path
) -> None:
    ledger = LaptopLedger(tmp_path / "ledger.jsonl")
    client = FakeSearch(lambda q, n: HITS)
    web = _web(config, sessions, ledger, client, use=BudgetUse.JUDGING)
    with pytest.raises(BudgetRefused, match="hosted") as refused:
        web.search("q", 5)
    assert refused.value.status == RunStatus.STOPPED_BUDGET
    assert client.sent == [] and ledger.entries() == []


def test_a_search_in_a_phase_with_no_cap_is_refused(
    config: Config, sessions: sessionmaker[Session], tmp_path: Path
) -> None:
    client = FakeSearch(lambda q, n: HITS)
    web = _web(config, sessions, LaptopLedger(tmp_path / "l.jsonl"), client, phase="9")
    with pytest.raises(BudgetRefused, match="no live-call cap"):
        web.search("q", 5)
    assert client.sent == []


def test_a_client_error_is_a_search_failure_with_no_ledger_line(
    config: Config, sessions: sessionmaker[Session], tmp_path: Path
) -> None:
    def broken(query: str, n: int) -> dict[str, Any]:
        raise SearchFailed("Tavily TimeoutError: slow")

    ledger = LaptopLedger(tmp_path / "ledger.jsonl")
    web = _web(config, sessions, ledger, FakeSearch(broken))
    with pytest.raises(SearchFailed):
        web.search("q", 5)
    assert ledger.entries() == []


def test_a_malformed_response_is_a_search_failure(
    config: Config, sessions: sessionmaker[Session], tmp_path: Path
) -> None:
    web = _web(
        config, sessions, LaptopLedger(tmp_path / "l.jsonl"), FakeSearch(lambda q, n: {"x": 1})
    )
    with pytest.raises(SearchFailed):
        web.search("q", 5)


def test_a_replay_serves_cached_searches_and_fails_loudly_on_a_miss(
    config: Config, sessions: sessionmaker[Session], tmp_path: Path
) -> None:
    ledger = LaptopLedger(tmp_path / "ledger.jsonl")
    _web(config, sessions, ledger, FakeSearch(lambda q, n: HITS)).search("q", 5)
    replay = _web(config, sessions, ledger, ReplaySearch())
    assert replay.search("q", 5).cache_hit
    with pytest.raises(ReplayMiss):
        replay.search("another query", 5)
