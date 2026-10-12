"""The structured logger: standard-library logging, one JSON object per line.

Pass structured fields as ``extra={"context": {...}}``.
"""

import json
import logging
from datetime import UTC, datetime

ROOT = "guideword"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        context = getattr(record, "context", None)
        if context is not None:
            entry["context"] = context
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str, ensure_ascii=False)


def get_logger(name: str) -> logging.Logger:
    """A logger under the guideword root; configure handlers once with configure()."""
    return logging.getLogger(name)


def configure(level: int = logging.INFO) -> None:
    """Send guideword logs to stderr as JSON lines. Safe to call more than once."""
    root = logging.getLogger(ROOT)
    if not any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        root.addHandler(handler)
    root.setLevel(level)
