"""The live model list: tier → model ID, with fallback (PROJECT.md §11 gateway step 1).

The list is fetched once per gateway and kept in memory. A tier whose expected model is
missing, or whose `shutdown_date` has passed, falls back along `fallback_order`.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from guideword.config import Config
from guideword.gateway.transport import Transport
from guideword.logs import get_logger
from guideword.schema.enums import Tier

log = get_logger(__name__)


class NoModel(RuntimeError):
    """No tier at or above the requested one is in the catalog."""


@dataclass(frozen=True)
class Resolved:
    tier: Tier
    model_id: str
    # the tiers skipped on the way, in order
    fell_back_from: tuple[Tier, ...] = ()


def _shut_down(entry: dict[str, Any], today: date) -> bool:
    value = entry.get("shutdown_date")
    if not value:
        return False
    try:
        return date.fromisoformat(str(value)[:10]) <= today
    except ValueError:
        # an unreadable date cannot prove the model is still served
        return True


class Catalog:
    def __init__(self, transport: Transport, config: Config, clock: Callable[[], datetime]) -> None:
        self._transport = transport
        self._config = config
        self._clock = clock
        self._entries: dict[str, dict[str, Any]] | None = None
        self._lock = threading.Lock()
        self.fetches = 0

    def _list(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            if self._entries is None:
                self._entries = {str(e["id"]): e for e in self._transport.models()}
                self.fetches += 1
            return self._entries

    def available(self, tier: Tier) -> bool:
        expected = self._config.models.tiers[tier].expected_id
        entry = self._list().get(expected)
        today = self._clock().astimezone(UTC).date()
        return entry is not None and not _shut_down(entry, today)

    def resolve(self, tier: Tier) -> Resolved:
        skipped: list[Tier] = []
        current: Tier | None = tier
        while current is not None:
            if self.available(current):
                if skipped:
                    log.warning(
                        "model tier fell back",
                        extra={"context": {"wanted": tier, "used": current, "skipped": skipped}},
                    )
                return Resolved(
                    current, self._config.models.tiers[current].expected_id, tuple(skipped)
                )
            skipped.append(current)
            current = self._config.routing.fallback_after(current)
        raise NoModel(f"no model for tier {tier} or any tier above it")
