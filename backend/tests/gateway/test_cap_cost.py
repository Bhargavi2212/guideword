"""R45: what a call counts against the run cap. A paid call counts its cost; a cache hit
counts the cost stored on the cache entry when it was written, never one recomputed from
current prices. An older entry with no stored cost is backfilled once from its tokens."""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from guideword.config import Config, load_config
from guideword.gateway.client import Gateway, RunBudget
from guideword.gateway.estimate import cost_usd
from guideword.gateway.fake import FakeTransport, fake_gateway, reply
from guideword.runs.db import ResponseCacheRow, make_session_factory
from guideword.schema.enums import Tier

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
MESSAGES = [{"role": "user", "content": "Is the sky blue? Answer yes or no."}]
RUN = "run:0123456789abcdef"


class Verdict(BaseModel):
    verdict: str
    reason: str


@pytest.fixture(scope="module")
def config() -> Config:
    return load_config(global_budget_usd=25.0)


@pytest.fixture
def sessions(tmp_path: Path) -> sessionmaker[Session]:
    return make_session_factory(f"sqlite:///{(tmp_path / 'g.db').as_posix()}")


def _ok(job: str, request: dict[str, Any]) -> Any:
    return reply({"verdict": "yes", "reason": "it is"}, input_tokens=1000, output_tokens=400)


def _build(
    config: Config, sessions: sessionmaker[Session], tmp_path: Path
) -> tuple[Gateway, FakeTransport]:
    return fake_gateway(
        config, _ok, sessions=sessions, ledger_path=tmp_path / "l.jsonl", clock=lambda: NOW
    )


def _call(gateway: Gateway) -> Any:
    return gateway.call(
        job="specialist_bulk",
        prompt_version="test/v1",
        messages=MESSAGES,
        schema=Verdict,
        run=RunBudget(RUN, 0.0, 1.0),
    )


def _rows(sessions: sessionmaker[Session]) -> list[ResponseCacheRow]:
    with sessions() as session:
        return list(session.query(ResponseCacheRow).all())


def _doubled_prices(config: Config) -> Config:
    tiers = {
        tier: model.model_copy(
            update={
                "input_usd_per_1m": model.input_usd_per_1m * 2,
                "output_usd_per_1m": model.output_usd_per_1m * 2,
            }
        )
        for tier, model in config.models.tiers.items()
    }
    return config.model_copy(update={"models": config.models.model_copy(update={"tiers": tiers})})


def test_paid_call_counts_its_cost_and_the_cache_stores_it(
    config: Config, sessions: sessionmaker[Session], tmp_path: Path
) -> None:
    gateway, _ = _build(config, sessions, tmp_path)
    result = _call(gateway)
    expected = cost_usd(config.models.tiers[Tier.LIGHTNING], 1000, 400)
    assert result.cost_usd == result.cap_cost_usd == pytest.approx(expected)
    [call] = result.model_calls
    assert call.cost_usd == call.cap_cost_usd == pytest.approx(expected)
    [row] = _rows(sessions)
    assert row.response["cost_usd"] == pytest.approx(expected)


def test_cache_hit_costs_nothing_and_counts_the_stored_cost(
    config: Config, sessions: sessionmaker[Session], tmp_path: Path
) -> None:
    gateway, transport = _build(config, sessions, tmp_path)
    paid = _call(gateway)
    hit = _call(gateway)
    assert len(transport.sent) == 1
    assert hit.cache_hit and hit.cost_usd == 0.0
    assert hit.cap_cost_usd == pytest.approx(paid.cost_usd)
    [call] = hit.model_calls
    assert (call.cache_hit, call.cost_usd) == (True, 0.0)
    assert call.cap_cost_usd == pytest.approx(paid.cost_usd)


def test_cache_hit_after_a_price_change_counts_the_stored_cost(
    config: Config, sessions: sessionmaker[Session], tmp_path: Path
) -> None:
    gateway, _ = _build(config, sessions, tmp_path)
    paid = _call(gateway)
    repriced, transport = _build(_doubled_prices(config), sessions, tmp_path)
    hit = _call(repriced)
    assert transport.sent == []
    assert hit.cap_cost_usd == pytest.approx(paid.cost_usd)


def _store_old_row(gateway: Gateway, sessions: sessionmaker[Session], **drop: bool) -> None:
    """Rewrite the stored row in the pre-R45 form: no stored cost (and, if asked, no tokens)."""
    with sessions.begin() as session:
        [row] = session.query(ResponseCacheRow).all()
        old = {k: v for k, v in row.response.items() if k != "cost_usd" and not drop.get(k)}
        row.response = old


def test_old_cache_row_is_backfilled_once_from_its_tokens(
    config: Config,
    sessions: sessionmaker[Session],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    gateway, transport = _build(config, sessions, tmp_path)
    paid = _call(gateway)
    _store_old_row(gateway, sessions)
    assert "cost_usd" not in _rows(sessions)[0].response
    with caplog.at_level(logging.INFO, logger="guideword.gateway.client"):
        hit = _call(gateway)
    assert len(transport.sent) == 1
    assert hit.cap_cost_usd == pytest.approx(paid.cost_usd)
    assert _rows(sessions)[0].response["cost_usd"] == pytest.approx(paid.cost_usd)
    assert [r.message for r in caplog.records] == ["cache cost backfill"]
    assert caplog.records[0].levelno == logging.INFO
    # later hits read the stored figure, even after a price change
    repriced, _ = _build(_doubled_prices(config), sessions, tmp_path)
    caplog.clear()
    again = _call(repriced)
    assert again.cap_cost_usd == pytest.approx(paid.cost_usd)
    assert caplog.records == []


def test_old_cache_row_without_tokens_counts_zero_with_a_warning(
    config: Config,
    sessions: sessionmaker[Session],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    gateway, transport = _build(config, sessions, tmp_path)
    _call(gateway)
    _store_old_row(gateway, sessions, input_tokens=True, output_tokens=True)
    with caplog.at_level(logging.INFO, logger="guideword.gateway.client"):
        hit = _call(gateway)
    assert len(transport.sent) == 1
    assert hit.cache_hit and hit.cap_cost_usd == 0.0
    assert [(r.levelno, r.message) for r in caplog.records] == [
        (logging.WARNING, "cached response has no stored cost and no token counts")
    ]
    assert "cost_usd" not in _rows(sessions)[0].response


def test_the_run_cap_is_checked_against_the_cap_figure(
    config: Config, sessions: sessionmaker[Session], tmp_path: Path
) -> None:
    """`RunBudget` carries the cap figure: a run whose cached spend fills its limit is refused
    a paid call even though it has paid nothing."""
    from guideword.gateway.client import BudgetRefused  # noqa: PLC0415

    gateway, transport = _build(config, sessions, tmp_path)
    with pytest.raises(BudgetRefused):
        gateway.call(
            job="specialist_bulk",
            prompt_version="test/v1",
            messages=MESSAGES,
            schema=Verdict,
            run=RunBudget(RUN, cap_spent_usd=1.0, limit_usd=1.0),
        )
    assert transport.sent == []
