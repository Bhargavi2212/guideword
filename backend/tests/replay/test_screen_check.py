"""`scripts/screen_check.py`: one plant_screen call on a plant, reported as validity and counts
only, never a hypothesis's words or rank. Fake transport only, no network."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import screen_check

from guideword.config import Config, load_config
from guideword.gateway.fake import FakeTransport, catalog_for, reply
from guideword.gateway.ledgers import LaptopLedger
from guideword.settings import Settings

REPO = Path(__file__).resolve().parents[3]
CASE_H = REPO / "cases" / "dev" / "case_h.json"
NOW = datetime(2026, 10, 17, 9, 0, tzinfo=UTC)
WORDS = "MECHANISM-WORDS-NEVER-PRINTED"


@pytest.fixture(scope="module")
def config() -> Config:
    """Without the safety net, so each test sees one call (the net is tested in test_step)."""
    shipped = load_config(global_budget_usd=25.0)
    run = shipped.caps.run.model_copy(update={"plant_screen_min_valid": 0})
    return shipped.model_copy(update={"caps": shipped.caps.model_copy(update={"run": run})})


def plant() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(CASE_H.read_text(encoding="utf-8"))
    return data


def hyp(rank: int, components: list[str], **extra: Any) -> dict[str, Any]:
    return {
        "rank": rank,
        "mechanism": f"{WORDS} {rank}",
        "component_ids": components,
        "chemical_ids": extra.get("chemicals", []),
        "failing_component_type": extra.get("kind", "external"),
        "cause_id": "outside_library",
        "cause_text": "outside",
        "consequence": f"{WORDS} consequence",
        "reason": f"{WORDS} reason",
        # Phase 9 (spec 9.1): the v4 card
        "initiating_event": f"{WORDS} start",
        "enabling_condition": f"{WORDS} condition",
        "propagation": f"{WORDS} path",
        "consequence_magnitude": None,
        "operating_mode": "normal",
        "mechanism_class": "other",
        "fact_ids": [],
    }


def run(tmp_path: Path, config: Config, answer: Any, *args: str) -> tuple[int, str, Any]:
    transport = FakeTransport(lambda job, request: reply(answer), catalog_for(config))
    code = screen_check.main(
        ["--use", "development", str(CASE_H), "--cap", "0.05", *args],
        transport=transport,
        config=config,
        settings=Settings(
            _env_file=None,  # type: ignore[call-arg]
            database_url=f"sqlite:///{(tmp_path / 's.db').as_posix()}",
        ),
        ledger=LaptopLedger(tmp_path / "l.jsonl"),
        clock=lambda: NOW,
    )
    return code, "", transport


def test_one_screen_call_only_and_counts_of_a_valid_answer(
    tmp_path: Path, config: Config, capsys: pytest.CaptureFixture[str]
) -> None:
    location = plant()["locations"][0]["id"]
    code, _, transport = run(tmp_path, config, {"hypotheses": [hyp(1, [location])]})
    out = capsys.readouterr().out
    assert code == 0
    assert [job for job, _ in transport.sent] == ["plant_screen"]
    assert "outcome ok" in out
    assert "returned 1, kept 1, dropped 0" in out
    assert "unknown component IDs 0, unknown chemical IDs 0" in out
    assert WORDS not in out and "rank" not in out.lower()


def test_unknown_ids_are_counted_and_drops_grouped_by_reason_without_text(
    tmp_path: Path, config: Config, capsys: pytest.CaptureFixture[str]
) -> None:
    location = plant()["locations"][0]["id"]
    answer = {
        "hypotheses": [
            hyp(1, [location]),
            hyp(2, ["NOT-AN-ID-1", "NOT-AN-ID-2"]),
            hyp(3, [location], chemicals=["NOT-A-CHEMICAL"]),
        ]
    }
    code, _, _ = run(tmp_path, config, answer)
    out = capsys.readouterr().out
    assert code == 0
    assert "outcome invalid" in out
    assert "returned 3, kept 1, dropped 2" in out
    assert "unknown component: 1" in out and "unknown chemical: 1" in out
    assert "unknown component IDs 2, unknown chemical IDs 1" in out
    for secret in (WORDS, "NOT-AN-ID", "NOT-A-CHEMICAL"):
        assert secret not in out


def test_an_unusable_answer_is_reported_as_such(
    tmp_path: Path, config: Config, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, _ = run(tmp_path, config, "not json at all")
    out = capsys.readouterr().out
    assert code == 0
    assert "returned 0, kept 0" in out and "answer invalid as a whole: 1" in out


def test_the_cap_is_required(tmp_path: Path, config: Config) -> None:
    with pytest.raises(SystemExit):
        screen_check.main(["--use", "development", str(CASE_H)], config=config)


def test_each_attempt_is_reported_and_the_kept_one_named(
    tmp_path: Path, config: Config, capsys: pytest.CaptureFixture[str]
) -> None:
    """B: a worse retry is reported but not kept."""
    location = plant()["locations"][0]["id"]
    good = [hyp(1, [location]), hyp(2, [location]) | {"mechanism": "other"}]
    first = {"hypotheses": [*good, hyp(3, ["NOT-AN-ID-1"])]}
    second = {"hypotheses": [good[0], hyp(2, ["NOT-AN-ID-2"])]}
    transport = FakeTransport(
        lambda job, request: reply(second if len(request["messages"]) > 2 else first),
        catalog_for(config),
    )
    screen_check.main(
        ["--use", "development", str(CASE_H), "--cap", "0.09"],
        transport=transport,
        config=config,
        settings=Settings(
            _env_file=None,  # type: ignore[call-arg]
            database_url=f"sqlite:///{(tmp_path / 's.db').as_posix()}",
        ),
        ledger=LaptopLedger(tmp_path / "l.jsonl"),
        clock=lambda: NOW,
    )
    out = capsys.readouterr().out
    assert "attempt 1: valid as a whole True, returned 3, passing 2" in out
    assert "attempt 2: valid as a whole True, returned 2, passing 1" in out
    assert "attempt kept: 1" in out
    assert "returned 3, kept 2, dropped 1" in out
    assert "NOT-AN-ID" not in out and WORDS not in out


# --- diagnostics: --prompt-file and --nonce (R50 review) ------------------------------------


def run_with(tmp_path: Path, config: Config, *args: str) -> tuple[int, Any]:
    transport = FakeTransport(lambda job, request: reply({"hypotheses": []}), catalog_for(config))
    code = screen_check.main(
        ["--use", "development", str(CASE_H), "--cap", "0.09", *args],
        transport=transport,
        config=config,
        settings=Settings(
            _env_file=None,  # type: ignore[call-arg]
            database_url=f"sqlite:///{(tmp_path / 's.db').as_posix()}",
        ),
        ledger=LaptopLedger(tmp_path / "l.jsonl"),
        clock=lambda: NOW,
    )
    return code, transport


def system_of(transport: Any) -> str:
    return str(transport.sent[0][1]["messages"][0]["content"])


def test_without_the_options_the_request_carries_the_run_marker(
    tmp_path: Path, config: Config
) -> None:
    _, transport = run_with(tmp_path, config)
    first, rest = system_of(transport).split("\n", 1)
    assert re.fullmatch(r"Request marker: run:[0-9a-f]{16}", first)
    assert rest.lstrip("\n").startswith("You are the first reviewer")


def test_nonce_is_the_very_first_line_of_the_system_message(tmp_path: Path, config: Config) -> None:
    code, transport = run_with(tmp_path, config, "--nonce", "h-check-4")
    assert code == 0
    first, rest = system_of(transport).split("\n", 1)
    assert first == "Request marker: h-check-4"
    assert rest.lstrip("\n").startswith("You are the first reviewer")


def test_a_nonce_with_a_line_break_is_refused(tmp_path: Path, config: Config) -> None:
    code, transport = run_with(tmp_path, config, "--nonce", "a\nb")
    assert code == 1 and transport.sent == []


def test_prompt_file_is_rendered_and_recorded_by_its_content(
    tmp_path: Path, config: Config
) -> None:
    shipped = (REPO / "prompts" / "plant_screen" / "v3.md").read_text(encoding="utf-8")
    alt = tmp_path / "alt.md"
    alt.write_text(
        shipped.replace("You are the first reviewer", "ALT-MARKER You are the first reviewer"),
        "utf-8",
    )
    code, transport = run_with(tmp_path, config, "--prompt-file", str(alt))
    assert code == 0
    assert (
        system_of(transport)
        .split("\n", 1)[1]
        .lstrip("\n")
        .startswith("ALT-MARKER You are the first reviewer")
    )
    import sqlite3  # noqa: PLC0415

    with sqlite3.connect(tmp_path / "s.db") as db:
        [(record,)] = list(db.execute("select record from model_calls"))
    assert json.loads(record)["prompt_version"].startswith("plant_screen/file-")


def test_the_reask_and_a_degraded_screen_are_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """With the shipped minimum: a short answer is re-asked once and the result reported."""
    shipped = load_config(global_budget_usd=25.0)
    location = plant()["locations"][0]["id"]
    run(tmp_path, shipped, {"hypotheses": [hyp(1, [location])]})
    out = capsys.readouterr().out
    assert "re-ask: yes" in out
    assert "attempt 2: valid as a whole True, returned 1, passing 1" in out
    assert "dropped, screen degraded: 1" in out
