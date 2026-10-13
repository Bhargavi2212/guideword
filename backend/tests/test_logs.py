"""The structured logger (decision D16)."""

import ast
import io
import json
import logging
from pathlib import Path

from guideword.logs import JsonFormatter, get_logger

PACKAGE = Path(__file__).resolve().parents[1] / "guideword"


def test_json_format() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = get_logger("guideword.test")
    logger.addHandler(handler)
    try:
        logger.warning("budget low", extra={"context": {"remaining_usd": 1.5}})
    finally:
        logger.removeHandler(handler)
    lines = stream.getvalue().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["level"] == "WARNING"
    assert record["logger"] == "guideword.test"
    assert record["message"] == "budget low"
    assert record["context"] == {"remaining_usd": 1.5}


def test_get_logger_is_under_guideword() -> None:
    assert get_logger("guideword.x").name == "guideword.x"


def test_no_print_in_package() -> None:
    offenders = []
    for path in PACKAGE.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "print"
            ):
                offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == []
