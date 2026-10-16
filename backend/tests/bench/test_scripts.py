"""The test #5 scripts (spec 2.10): fake transport, synthetic keys in tmp_path, no network."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import run_test5a
import score_test5
import test5_results

from guideword.bench.results import HAND_SCORES, SCORES
from guideword.config import Config, load_config
from guideword.gateway.fake import FakeTransport, catalog_for, reply
from guideword.gateway.ledgers import LaptopLedger
from guideword.settings import Settings

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def config() -> Config:
    return load_config(global_budget_usd=25.0)


def _key(tmp_path: Path) -> Path:
    path = tmp_path / "keys.json"
    path.write_text(
        json.dumps(
            {
                "_note": "synthetic",
                "case_g_batch_plant": {
                    "source": "s",
                    "actual_event": "e",
                    "match": [["chlorine"], ["dead leg"]],
                    "memorization_markers": [],
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _5b(root: Path) -> None:
    (root / "5b").mkdir(parents=True)
    ranked = [
        {
            "rank": 1,
            "text": "chlorine — dead leg rupture",
            "question_id": "q:x",
            "failing_component_ids": ["L-1"],
            "finding_id": "f:1",
        }
    ]
    report = {"status": "finished", "spent_usd": 0.2, "seconds": 60.0, "ranked": ranked}
    (root / "5b" / "case_g.json").write_text(json.dumps(report), encoding="utf-8")


def test_score_script_never_reads_keys_in_tests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    real = Path.read_text

    def guarded(self: Path, *args: Any, **kwargs: Any) -> str:
        if self.resolve() == score_test5.DEFAULT_KEYS.resolve():
            raise AssertionError("the real answer key was read")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded)
    root = tmp_path / "test5"
    _5b(root)
    code = score_test5.main(["--case", "g", "--keys", str(_key(tmp_path)), "--root", str(root)])
    assert code == 0
    scores = json.loads((root / SCORES).read_text(encoding="utf-8"))
    assert scores["g"]["5b"]["rank"] == 1 and scores["g"]["5a"]["status"] == "not run"
    assert (root / HAND_SCORES).exists()
    out = capsys.readouterr().out
    assert "case_g 5B: rank 1 (top3)" in out


def test_score_script_refuses_a_case_the_key_does_not_have(tmp_path: Path) -> None:
    root = tmp_path / "test5"
    _5b(root)
    code = score_test5.main(["--case", "d", "--keys", str(_key(tmp_path)), "--root", str(root)])
    assert code == 1


def test_scores_of_other_cases_are_kept(tmp_path: Path) -> None:
    root = tmp_path / "test5"
    _5b(root)
    (root / SCORES).write_text(json.dumps({"d": {"5b": {"x": 1}, "5a": {"x": 2}}}), "utf-8")
    score_test5.main(["--case", "g", "--keys", str(_key(tmp_path)), "--root", str(root)])
    assert set(json.loads((root / SCORES).read_text(encoding="utf-8"))) == {"d", "g"}


def test_results_script_writes_results_md(tmp_path: Path) -> None:
    root = tmp_path / "test5"
    _5b(root)
    score_test5.main(["--case", "g", "--keys", str(_key(tmp_path)), "--root", str(root)])
    assert test5_results.main(["--root", str(root)]) == 0
    text = (root / "results.md").read_text(encoding="utf-8")
    assert "| case_g | 5B | finished | 1 | top3 | not scored | 0.2000 | 60 |" in text


def test_run_test5a_calls_ultra_once_per_case_under_test_5(tmp_path: Path, config: Config) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "case_d_x.md").write_text("package", encoding="utf-8")
    answer = {"hazards": [{"rank": 1, "hazard": "a — b", "equipment": [], "reason": "r"}]}
    transport = FakeTransport(lambda job, request: reply(answer), catalog_for(config))
    code = run_test5a.main(
        ["--case", "d", "--use", "test_5"],
        transport=transport,
        config=config,
        settings=Settings(
            _env_file=None,  # type: ignore[call-arg]
            database_url=f"sqlite:///{(tmp_path / 'g.db').as_posix()}",
        ),
        ledger=LaptopLedger(tmp_path / "l.jsonl"),
        clock=lambda: NOW,
        source_dir=source,
        out_root=tmp_path / "test5",
    )
    assert code == 0 and len(transport.sent) == 1
    assert (tmp_path / "test5" / "5a" / "case_d.json").exists()
    ledger = [json.loads(x) for x in (tmp_path / "l.jsonl").read_text("utf-8").splitlines()]
    assert [line["use"] for line in ledger] == ["test_5"]
