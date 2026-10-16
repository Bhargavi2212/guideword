"""The response cache (decision R15): the `response_cache` table, keyed by
`ids.cache_key(model ID, prompt version, exact input)`.

Each write is committed on its own, outside any step's transaction, so a step that fails
after a paid call never loses the response: the next attempt is a cache hit (spec 2.1).

Each entry also stores the original call's cost (R45), so a hit counts against the run cap
exactly what the original call cost, whatever the price table says later.
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from guideword.gateway.transport import Reply
from guideword.runs.db import ResponseCacheRow

COST_KEY = "cost_usd"
TOKEN_KEYS = ("input_tokens", "output_tokens")


@dataclass(frozen=True)
class Cached:
    reply: Reply
    # the original call's cost; None on an entry written before R45
    cost_usd: float | None
    # False when the stored entry has no token counts to work a cost out from
    has_tokens: bool


class ResponseCache:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def get(self, key: str) -> Cached | None:
        with self._sessions() as session:
            row = session.get(ResponseCacheRow, key)
            if row is None:
                return None
            data = row.response
            has_tokens = all(data.get(k) is not None for k in TOKEN_KEYS)
            reply = Reply.from_json({**data, **{k: data.get(k) or 0 for k in TOKEN_KEYS}})
            stored = data.get(COST_KEY)
            return Cached(reply, None if stored is None else float(stored), has_tokens)

    def put(
        self, key: str, model_id: str, prompt_version: str, reply: Reply, cost_usd: float
    ) -> None:
        with self._sessions.begin() as session:
            session.merge(
                ResponseCacheRow(
                    key=key,
                    model_id=model_id,
                    prompt_version=prompt_version,
                    response={**reply.to_json(), COST_KEY: cost_usd},
                )
            )

    def store_cost(self, key: str, cost_usd: float) -> None:
        """Write the cost into an older entry that has none (the R45 backfill), once."""
        with self._sessions.begin() as session:
            row = session.get(ResponseCacheRow, key)
            if row is not None and row.response.get(COST_KEY) is None:
                row.response = {**row.response, COST_KEY: cost_usd}

    def entry(self, key: str) -> tuple[str, str, dict[str, Any]] | None:
        """(model ID, prompt version, stored response) as written, for the replay export."""
        with self._sessions() as session:
            row = session.get(ResponseCacheRow, key)
            return None if row is None else (row.model_id, row.prompt_version, dict(row.response))

    def put_entry(
        self, key: str, model_id: str, prompt_version: str, response: dict[str, Any]
    ) -> None:
        """Store an exported entry unchanged (loading replay fixtures)."""
        with self._sessions.begin() as session:
            session.merge(
                ResponseCacheRow(
                    key=key, model_id=model_id, prompt_version=prompt_version, response=response
                )
            )

    def keys(self) -> list[str]:
        with self._sessions() as session:
            return sorted(r.key for r in session.query(ResponseCacheRow).all())
