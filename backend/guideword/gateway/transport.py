"""How the gateway reaches Token Factory: a small transport the tests replace with a fake.

The real transport wraps the OpenAI-compatible client with its own retries off (the gateway
retries, under the budget guard). Responses are reduced to a `Reply` holding only what the
gateway needs: the answer text, reasoning, tool calls, finish reason and token usage.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import openai

from guideword.settings import Settings

RETRIABLE_STATUS = 429


@dataclass(frozen=True)
class ToolCallRequest:
    """A tool the model asked to call; `arguments` is the raw JSON text it sent."""

    call_id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class Reply:
    content: str | None
    reasoning: str | None
    tool_calls: tuple[ToolCallRequest, ...] = ()
    finish_reason: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    # the response as returned, minus headers; never holds a key
    raw: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "reasoning": self.reasoning,
            "tool_calls": [
                {"call_id": t.call_id, "name": t.name, "arguments": t.arguments}
                for t in self.tool_calls
            ],
            "finish_reason": self.finish_reason,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "raw": self.raw,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Reply":
        return cls(
            content=data["content"],
            reasoning=data["reasoning"],
            tool_calls=tuple(ToolCallRequest(**t) for t in data["tool_calls"]),
            finish_reason=data["finish_reason"],
            input_tokens=data["input_tokens"],
            output_tokens=data["output_tokens"],
            raw=data["raw"],
        )


class TransportError(RuntimeError):
    """The service refused or failed the request; `status` is the HTTP status if any."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status

    @property
    def retriable(self) -> bool:
        return self.status is not None and (self.status == RETRIABLE_STATUS or self.status >= 500)


class Transport(Protocol):
    def models(self) -> list[dict[str, Any]]: ...

    def send(self, job: str, request: dict[str, Any]) -> Reply: ...


class OpenAITransport:
    """Token Factory through the OpenAI-compatible client. Only the gateway imports openai."""

    def __init__(self, settings: Settings, factory: Callable[[], Any] | None = None) -> None:
        self._settings = settings
        self._factory = factory
        self._client: Any = None

    def _openai(self) -> Any:
        if self._client is None:
            if self._factory is not None:
                self._client = self._factory()
            else:
                key = self._settings.nebius_api_key.get_secret_value()
                if not key:
                    raise TransportError("NEBIUS_API_KEY is not set")
                self._client = openai.OpenAI(
                    base_url=self._settings.nebius_base_url, api_key=key, max_retries=0
                )
        return self._client

    def models(self) -> list[dict[str, Any]]:
        try:
            return [dict(m.model_dump()) for m in self._openai().models.list().data]
        except openai.APIStatusError as error:
            raise TransportError(error.message, error.status_code) from error
        except openai.APIError as error:
            raise TransportError(error.message) from error

    def send(self, job: str, request: dict[str, Any]) -> Reply:
        try:
            response = self._openai().chat.completions.create(**request)
        except openai.APIStatusError as error:
            raise TransportError(
                f"{type(error).__name__}: {error.message}", error.status_code
            ) from error
        except openai.APIError as error:
            raise TransportError(f"{type(error).__name__}: {error.message}") from error
        choice = response.choices[0]
        message = choice.message
        usage = response.usage
        calls = tuple(
            ToolCallRequest(call_id=c.id, name=c.function.name, arguments=c.function.arguments)
            for c in (message.tool_calls or ())
        )
        return Reply(
            content=message.content,
            reasoning=getattr(message, "reasoning_content", None),
            tool_calls=calls,
            finish_reason=choice.finish_reason,
            input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            raw=response.model_dump(mode="json"),
        )
