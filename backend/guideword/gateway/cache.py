"""The response cache (decision R15): the `response_cache` table, keyed by
`ids.cache_key(model ID, prompt version, exact input)`.

Each write is committed on its own, outside any step's transaction, so a step that fails
after a paid call never loses the response: the next attempt is a cache hit (spec 2.1).
"""

from sqlalchemy.orm import Session, sessionmaker

from guideword.gateway.transport import Reply
from guideword.runs.db import ResponseCacheRow


class ResponseCache:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def get(self, key: str) -> Reply | None:
        with self._sessions() as session:
            row = session.get(ResponseCacheRow, key)
            return None if row is None else Reply.from_json(row.response)

    def put(self, key: str, model_id: str, prompt_version: str, reply: Reply) -> None:
        with self._sessions.begin() as session:
            session.merge(
                ResponseCacheRow(
                    key=key,
                    model_id=model_id,
                    prompt_version=prompt_version,
                    response=reply.to_json(),
                )
            )

    def keys(self) -> list[str]:
        with self._sessions() as session:
            return sorted(r.key for r in session.query(ResponseCacheRow).all())
