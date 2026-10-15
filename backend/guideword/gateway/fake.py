"""A fake transport for tests: scripted replies, counted calls, never the network.

`FakeTransport(script)` calls `script(job, request)` for each send; the script returns a
`Reply` or raises `TransportError`. `fake_gateway(...)` builds a real `Gateway` on it, so
every guard, the cache and the ledger behave exactly as in a live run.
"""

import json
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from guideword.config import Config
from guideword.gateway.cache import ResponseCache
from guideword.gateway.client import Gateway
from guideword.gateway.ledgers import LaptopLedger, Ledger
from guideword.gateway.transport import Reply
from guideword.schema.enums import BudgetUse

Script = Callable[[str, dict[str, Any]], Reply]


def reply(
    content: Any = None,
    *,
    tool_calls: tuple[Any, ...] = (),
    finish_reason: str = "stop",
    input_tokens: int = 100,
    output_tokens: int = 50,
    reasoning: str | None = None,
) -> Reply:
    """A reply; a dict or list `content` is sent as its JSON text."""
    text = content if isinstance(content, str) or content is None else json.dumps(content)
    return Reply(
        content=text,
        reasoning=reasoning,
        tool_calls=tuple(tool_calls),
        finish_reason="tool_calls" if tool_calls and finish_reason == "stop" else finish_reason,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        raw={"fake": True, "content": text},
    )


class FakeTransport:
    def __init__(self, script: Script, models: list[dict[str, Any]] | None = None) -> None:
        self._script = script
        self._models = models
        self.sent: list[tuple[str, dict[str, Any]]] = []
        self.model_list_calls = 0
        self._lock = threading.Lock()

    def models(self) -> list[dict[str, Any]]:
        self.model_list_calls += 1
        return list(self._models or [])

    def send(self, job: str, request: dict[str, Any]) -> Reply:
        with self._lock:
            self.sent.append((job, request))
        return self._script(job, request)


def catalog_for(config: Config, **shutdown: str) -> list[dict[str, Any]]:
    """The model list with every expected ID present; `shutdown` maps tier → date."""
    return [
        {"id": t.expected_id, "shutdown_date": shutdown.get(str(tier), "")}
        for tier, t in config.models.tiers.items()
    ]


def fake_gateway(
    config: Config,
    script: Script,
    *,
    sessions: sessionmaker[Session],
    ledger_path: Path,
    clock: Callable[[], datetime],
    use: BudgetUse = BudgetUse.DEVELOPMENT,
    phase: str = "2",
    models: list[dict[str, Any]] | None = None,
    ledger: Ledger | None = None,
    sleep: Callable[[float], None] | None = None,
) -> tuple[Gateway, FakeTransport]:
    transport = FakeTransport(script, models if models is not None else catalog_for(config))
    gateway = Gateway(
        config=config,
        transport=transport,
        cache=ResponseCache(sessions),
        ledger=ledger if ledger is not None else LaptopLedger(ledger_path),
        use=use,
        phase=phase,
        clock=clock,
        sleep=sleep if sleep is not None else (lambda seconds: None),
        timer=lambda: 0.0,
    )
    return gateway, transport
