"""Tavily web search, the only Tavily caller in the product (PROJECT.md §11 call boundaries;
Phase 4 spec 4.3 rules; plan PR 5a, Q14, G6, G18).

`WebSearch.search` serves an exact query from the response cache, else checks the call is
allowed (the use belongs to this environment's ledger, the phase has a cap) and sends it
through the injected client, then caches the response and writes one ledger line (`kind:
tavily`, `searches: 1`, cost 0: Tavily credits are separate from the $25) to this environment's
ledger, laptop or hosted. Its results are data, never instructions.

The per-run search cap (`evidence.tavily_searches_per_run`) is the evidence step's, counted
from the run's own tool calls. A replay uses `ReplaySearch`: the fixtures are loaded into the
cache, and any search they don't hold raises `ReplayMiss`.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

import tavily  # type: ignore[import-untyped]

from guideword.config import Config
from guideword.gateway.cache import ResponseCache
from guideword.gateway.client import BudgetRefused
from guideword.gateway.ledgers import Ledger
from guideword.gateway.replay import ReplayMiss
from guideword.schema import ids
from guideword.schema.enums import BudgetUse, RunStatus
from guideword.schema.records import SpendEntry

# the cache's "model" and "prompt version" for a search (no new table, plan G18)
SEARCH_MODEL = "tavily"
SEARCH_VERSION = "search/v1"
SCRIPT = "tools"
PURPOSE = "web_research"
# the errors the Tavily client raises; OSError covers network failures
TAVILY_ERRORS: tuple[type[BaseException], ...] = (
    tavily.errors.UsageLimitExceededError,
    tavily.errors.BadRequestError,
    tavily.errors.ForbiddenError,
    tavily.errors.InvalidAPIKeyError,
    tavily.errors.TimeoutError,
    OSError,
)


class SearchFailed(RuntimeError):
    """The search was sent and failed, or its response had no result list; nothing cached."""


class SearchClient(Protocol):
    def search(self, query: str, max_results: int) -> dict[str, Any]: ...


@dataclass(frozen=True)
class WebHit:
    title: str
    url: str
    content: str


@dataclass(frozen=True)
class SearchResult:
    query: str
    max_results: int
    hits: tuple[WebHit, ...]
    # the response-cache key, recorded on the tool call so a replay export finds it
    cache_key: str
    cache_hit: bool


def search_cache_key(query: str, max_results: int) -> str:
    return ids.cache_key(SEARCH_MODEL, SEARCH_VERSION, {"query": query, "max_results": max_results})


def _hits(response: dict[str, Any]) -> tuple[WebHit, ...]:
    results = response.get("results")
    if not isinstance(results, list):
        raise SearchFailed("the search response has no result list")
    return tuple(
        WebHit(str(r.get("title") or ""), str(r["url"]), str(r.get("content") or ""))
        for r in results
        if isinstance(r, dict) and isinstance(r.get("url"), str) and r["url"]
    )


class WebSearch:
    def __init__(
        self,
        *,
        client: SearchClient,
        cache: ResponseCache,
        ledger: Ledger,
        config: Config,
        use: BudgetUse,
        phase: str,
        clock: Callable[[], datetime],
    ) -> None:
        self._client = client
        self._cache = cache
        self._ledger = ledger
        self._config = config
        self.use = BudgetUse(use)
        self.phase = phase
        self._clock = clock

    def search(self, query: str, max_results: int) -> SearchResult:
        key = search_cache_key(query, max_results)
        stored = self._cache.get_tool(key)
        if stored is not None:
            return SearchResult(query, max_results, _hits(stored), key, True)
        self._check()
        response = self._client.search(query, max_results)
        hits = _hits(response)
        self._cache.put_tool(key, SEARCH_MODEL, SEARCH_VERSION, response)
        self._ledger.append(
            SpendEntry(
                ts=self._clock(),
                kind="tavily",
                environment=self._ledger.environment,
                phase=self.phase,
                use=self.use,
                searches=1,
                cost_usd=0.0,
                script=SCRIPT,
                purpose=PURPOSE,
            )
        )
        return SearchResult(query, max_results, hits, key, False)

    def _check(self) -> None:
        """Refused before sending, as the gateway refuses a model call (cost 0, so only the
        phase and the environment can refuse it)."""
        caps = self._config.caps
        if self.phase not in caps.phase_caps_usd:
            raise BudgetRefused(
                f"phase {self.phase} has no live-call cap in caps.yaml", RunStatus.STOPPED_BUDGET
            )
        environment = self._ledger.environment
        if caps.environment_of(self.use) != environment:
            raise BudgetRefused(
                f"use {self.use} belongs to the {caps.environment_of(self.use)} allowance, "
                f"not {environment}",
                RunStatus.STOPPED_BUDGET,
            )


class TavilySearch:
    """The live client. Only Bhargavi runs it, under a spend cap."""

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("TAVILY_API_KEY is not set")
        self._client = tavily.TavilyClient(api_key=api_key)

    def search(self, query: str, max_results: int) -> dict[str, Any]:
        try:
            response = self._client.search(query=query, max_results=max_results)
        except TAVILY_ERRORS as error:
            raise SearchFailed(f"Tavily {type(error).__name__}: {error}") from error
        if not isinstance(response, dict):
            raise SearchFailed("the search response is not an object")
        return response


class ReplaySearch:
    """A replay: every search must come from the fixtures in the cache."""

    def search(self, query: str, max_results: int) -> dict[str, Any]:
        raise ReplayMiss(f"no replay fixture for a web search ({max_results} results)")


@dataclass
class FakeSearch:
    """A scripted client for tests: `script(query, max_results)` returns the response."""

    script: Callable[[str, int], dict[str, Any]]
    sent: list[tuple[str, int]] = field(default_factory=list)

    def search(self, query: str, max_results: int) -> dict[str, Any]:
        self.sent.append((query, max_results))
        return self.script(query, max_results)
