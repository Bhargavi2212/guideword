"""`scripts/export_replay.py` (spec 2.9): no calls; reads the run store only."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import export_replay
import pytest
import run_case

from guideword.config import Config, load_config
from guideword.gateway.fake import FakeTransport, catalog_for
from guideword.gateway.ledgers import LaptopLedger
from guideword.gateway.replay import MANIFEST
from guideword.settings import Settings

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def config() -> Config:
    return load_config(global_budget_usd=25.0)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        database_url=f"sqlite:///{(tmp_path / 'g.db').as_posix()}",
    )


def _run(tmp_path: Path, config: Config, script: Any) -> str:
    run_case.main(
        ["--use", "development", str(EXAMPLE)],
        transport=FakeTransport(script, catalog_for(config)),
        config=config,
        settings=_settings(tmp_path),
        ledger=LaptopLedger(tmp_path / "l.jsonl"),
        clock=lambda: NOW,
        out_dir=tmp_path / "5b",
    )
    run_id: str = json.loads((tmp_path / "5b" / f"{EXAMPLE.stem}.json").read_text("utf-8"))[
        "run_id"
    ]
    return run_id


def test_export_writes_the_case_folder(tmp_path: Path, config: Config, script: Any) -> None:
    run_id = _run(tmp_path, config, script)
    code = export_replay.main(
        [run_id, str(EXAMPLE)], config=config, settings=_settings(tmp_path), out_root=tmp_path / "r"
    )
    assert code == 0
    manifest = json.loads((tmp_path / "r" / EXAMPLE.stem / MANIFEST).read_text("utf-8"))
    assert manifest["run_id"] == run_id and manifest["case"] == EXAMPLE.stem


def test_export_refuses_a_plant_the_run_was_not_started_from(
    tmp_path: Path, config: Config, script: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    run_id = _run(tmp_path, config, script)
    other = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    other["plant_id"] = "another_plant"
    path = tmp_path / "other.json"
    path.write_text(json.dumps(other), encoding="utf-8")
    code = export_replay.main(
        [run_id, str(path)], config=config, settings=_settings(tmp_path), out_root=tmp_path / "r"
    )
    assert code == 1
    assert "not the plant" in capsys.readouterr().err
    assert not (tmp_path / "r").exists()


def test_export_of_an_unknown_run_is_refused(tmp_path: Path, config: Config) -> None:
    code = export_replay.main(
        ["run:0000000000000000", str(EXAMPLE)],
        config=config,
        settings=_settings(tmp_path),
        out_root=tmp_path / "r",
    )
    assert code == 1
