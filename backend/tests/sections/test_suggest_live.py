"""The live section suggester (spec 2.7; plan PR 9, R9, R22, R23): Super through the gateway,
validated, refused above `section_suggest_cap_usd`, booked to `development` with no ModelCall
record. Fake transport only."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from guideword.api import models as api
from guideword.api.app import create_app
from guideword.api.suggester import GatewaySuggester
from guideword.config import Config, load_config
from guideword.gateway.client import Gateway
from guideword.gateway.fake import fake_gateway, reply
from guideword.gateway.ledgers import LaptopLedger
from guideword.schema.plant import Plant
from guideword.sections.rules import rule_cut
from guideword.settings import Settings

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
NOW = datetime(2026, 10, 17, 9, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def config() -> Config:
    return load_config(global_budget_usd=25.0)


def _plant() -> Plant:
    return Plant.model_validate(json.loads(EXAMPLE.read_text(encoding="utf-8")))


def _answer(sections: list[Any]) -> dict[str, Any]:
    """One valid purpose on a real section, one merge of a section that does not exist."""
    return {
        "suggestions": [
            {
                "kind": "purpose",
                "section_ids": [
                    sections[0]["id"] if isinstance(sections[0], dict) else sections[0].id
                ],
                "purpose": "Charge and mix the batch",
                "reason": "the mixer is where the batch is made",
            },
            {
                "kind": "merge",
                "section_ids": ["S-NOPE-1", "S-NOPE-2"],
                "purpose": None,
                "reason": "they belong together",
            },
        ]
    }


def _gateway(tmp_path: Path, config: Config, answer: Any) -> tuple[Gateway, Any]:
    from guideword.runs.db import make_session_factory  # noqa: PLC0415

    sessions = make_session_factory(f"sqlite:///{(tmp_path / 'g.db').as_posix()}")
    return fake_gateway(
        config,
        lambda job, request: reply(answer),
        sessions=sessions,
        ledger_path=tmp_path / "ledger.jsonl",
        clock=lambda: NOW,
    )


def test_the_suggester_calls_super_once_and_validates_the_answer(
    tmp_path: Path, config: Config
) -> None:
    plant = _plant()
    sections = rule_cut(plant, "plant:x:0")
    gateway, transport = _gateway(tmp_path, config, _answer(sections))
    suggestions = GatewaySuggester(gateway, config).suggest(plant, sections)
    assert [job for job, _ in transport.sent] == ["section_suggestion"]
    assert transport.sent[0][1]["model"] == config.models.tiers["super"].expected_id
    assert [s.kind for s in suggestions] == ["purpose", "merge"]  # code checks them later
    [entry] = LaptopLedger(tmp_path / "ledger.jsonl").entries()
    assert entry.use == "development"


def test_the_cap_refuses_a_call_that_would_exceed_it(tmp_path: Path, config: Config) -> None:
    plant_caps = config.caps.plant.model_copy(update={"section_suggest_cap_usd": 0.000001})
    tight = config.model_copy(update={"caps": config.caps.model_copy(update={"plant": plant_caps})})
    plant = _plant()
    sections = rule_cut(plant, "plant:x:0")
    gateway, transport = _gateway(tmp_path, tight, _answer(sections))
    assert GatewaySuggester(gateway, tight).suggest(plant, sections) == []
    assert transport.sent == []


def test_an_invalid_answer_gives_no_suggestions(tmp_path: Path, config: Config) -> None:
    plant = _plant()
    sections = rule_cut(plant, "plant:x:0")
    gateway, _ = _gateway(tmp_path, config, {"suggestions": [{"kind": "explode"}]})
    assert GatewaySuggester(gateway, config).suggest(plant, sections) == []


# --- the propose endpoint ------------------------------------------------------------------


def _client(tmp_path: Path, config: Config, gateway_factory: Any = None) -> TestClient:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        guideword_mock=False,
        database_url=f"sqlite:///{(tmp_path / 'api.db').as_posix()}",
    )
    return TestClient(
        create_app(
            settings=settings,
            clock=lambda: NOW,
            gateway_factory=gateway_factory,
            ledger=LaptopLedger(tmp_path / "ledger.jsonl"),
        )
    )


def _propose(client: TestClient) -> api.SectionProposal:
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    record_id = client.post("/plants", json=data).json()["plant_record_id"]
    response = client.post(f"/plants/{quote(record_id, safe='')}/sections/propose")
    assert response.status_code == 200, response.text
    return api.SectionProposal.model_validate(response.json())


def test_valid_returned_rejected_returned_with_reasons(tmp_path: Path, config: Config) -> None:
    sections = rule_cut(_plant(), "plant:x:0")

    def factory(sessions: sessionmaker[Session]) -> Gateway:
        gateway, _ = fake_gateway(
            config,
            lambda job, request: reply(_answer(sections)),
            sessions=sessions,
            ledger_path=tmp_path / "ledger.jsonl",
            clock=lambda: NOW,
        )
        return gateway

    proposal = _propose(_client(tmp_path, config, factory))
    assert [s.kind for s in proposal.suggestions] == ["purpose"]
    [rejected] = proposal.rejected
    assert rejected.suggestion.kind == "merge"
    assert "unknown section" in rejected.reason


def test_null_suggester_still_used_without_a_gateway(
    tmp_path: Path, config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No injected gateway and no API key: no call is attempted and nothing is suggested."""
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    proposal = _propose(_client(tmp_path, config))
    assert proposal.suggestions == [] and proposal.rejected == []
