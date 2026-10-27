"""The probe, the two baselines and the probe judgement (Phase 6 spec 6.2, 6.3, P6-4, P6-5,
P6-13; plan PR 2, G3, G4, G7; acceptance 2b, 4). Fake gateway, synthetic packages and keys."""

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from guideword.bench.probe import (
    JOB as PROBE_JOB,
)
from guideword.bench.probe import (
    JudgementRefused,
    ProbeAnswer,
    judgement_rows,
    read_judgement,
    run_probe,
    write_judgement,
)
from guideword.bench.test5a import BASELINE_B, run_baseline
from guideword.config import Config, load_config
from guideword.gateway.fake import fake_gateway, reply
from guideword.runs.case import OUTSIDE_RUN_JOBS, run_settings
from guideword.runs.db import make_session_factory
from guideword.schema.enums import BudgetUse, Tier

NOW = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)
PACKAGE = "# Case K package\n\nA tank, a pump and a valve."
SECRET = "SENTINEL-the-root-cause-is-a-secret"


@pytest.fixture(scope="module")
def config() -> Config:
    return load_config(global_budget_usd=25.0)


def _hazards() -> dict[str, Any]:
    return {
        "hazards": [
            {"rank": 1, "hazard": "cause — consequence", "equipment": ["T-1"], "reason": "r"}
        ]
    }


def _probe(recognised: bool = False) -> dict[str, Any]:
    return {
        "recognised": recognised,
        "company": None,
        "site": None,
        "year": None,
        "accident_name": None,
        "reason": "nothing in the package names a known accident",
    }


def _setup(
    tmp_path: Path, config: Config, answer: Any, finish_reason: str = "stop"
) -> tuple[Any, Any, Path, Path]:
    source = tmp_path / "heldout"
    source.mkdir()
    (source / "case_k_tank_farm.md").write_text(PACKAGE, encoding="utf-8")
    sessions = make_session_factory(f"sqlite:///{(tmp_path / 'b.db').as_posix()}")
    gateway, transport = fake_gateway(
        config,
        lambda job, request: reply(answer, finish_reason=finish_reason),
        sessions=sessions,
        ledger_path=tmp_path / "ledger.jsonl",
        clock=lambda: NOW,
        use=BudgetUse.BENCHMARK,
        phase="6",
    )
    return gateway, transport, source, tmp_path / "out"


def _ledger(tmp_path: Path) -> list[dict[str, Any]]:
    lines = (tmp_path / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


# --- P6-13, G3, G4: the config ----------------------------------------------------------------


def test_the_two_new_jobs_route_to_ultra_with_their_prompts(config: Config) -> None:
    for job in ("probe", "baseline_plain"):
        assert config.routing.jobs[job] == Tier.ULTRA
        assert config.routing.prompts[job] == "v1"
        assert config.caps.run.max_tokens[job] > 0
    assert set(OUTSIDE_RUN_JOBS) == {"probe", "baseline_plain"}


def _without(config: Config) -> Config:
    routing = config.routing.model_copy(
        update={
            "jobs": {k: v for k, v in config.routing.jobs.items() if k not in OUTSIDE_RUN_JOBS},
            "prompts": {
                k: v for k, v in config.routing.prompts.items() if k not in OUTSIDE_RUN_JOBS
            },
        }
    )
    run = config.caps.run.model_copy(
        update={
            "max_tokens": {
                k: v for k, v in config.caps.run.max_tokens.items() if k not in OUTSIDE_RUN_JOBS
            }
        }
    )
    caps = config.caps.model_copy(update={"run": run})
    return config.model_copy(update={"routing": routing, "caps": caps})


def test_run_settings_are_identical_with_and_without_the_outside_run_jobs(
    config: Config,
) -> None:
    """Acceptance 2b: job, prompt and max_tokens entries never reach a run's hash, so a
    Guideword run's ID is unchanged by them."""
    assert run_settings(config) == run_settings(_without(config))
    settings = run_settings(config)
    assert not OUTSIDE_RUN_JOBS & set(settings.routing_config)
    assert not OUTSIDE_RUN_JOBS & set(settings.prompt_versions)
    assert not OUTSIDE_RUN_JOBS & set(settings.caps["max_tokens"])
    assert settings.routing_config["test5a"] == "ultra"  # 5A stays hashed, as every run has it


def test_the_benchmark_block_is_hash_free_and_its_stop_is_the_sum(config: Config) -> None:
    bench = config.caps.benchmark
    assert (bench.run_cap_usd, bench.post_cap_usd, bench.baselines_usd) == (1.40, 0.30, 0.05)
    assert bench.stop_below_usd == pytest.approx(1.75)
    assert "benchmark" not in config.caps.run_input_caps()
    changed = config.model_copy(
        update={
            "caps": config.caps.model_copy(
                update={"benchmark": bench.model_copy(update={"run_cap_usd": 9.0})}
            )
        }
    )
    assert run_settings(changed) == run_settings(config)


def test_a_stop_rule_that_isnt_the_sum_is_refused(config: Config) -> None:
    from guideword.config import BenchmarkCaps

    with pytest.raises(ValidationError, match="stop_below_usd"):
        BenchmarkCaps(run_cap_usd=1.4, post_cap_usd=0.3, baselines_usd=0.05, stop_below_usd=1.3)


# --- the probe --------------------------------------------------------------------------------


def test_probe_schema_needs_a_reason_and_allows_empty_names() -> None:
    assert ProbeAnswer.model_validate(_probe()).recognised is False
    with pytest.raises(ValidationError):
        ProbeAnswer.model_validate({k: v for k, v in _probe().items() if k != "reason"})
    named = ProbeAnswer.model_validate(_probe(True) | {"company": "A Co", "year": "1999"})
    assert named.year == "1999"


def test_the_probe_writes_under_the_given_root_with_use_benchmark_and_phase_6(
    tmp_path: Path, config: Config
) -> None:
    gateway, transport, source, out = _setup(tmp_path, config, _probe())
    record = run_probe(gateway, config, "k", source_dir=source, out_root=out)
    [(job, request)] = transport.sent
    assert job == PROBE_JOB and request["model"] == config.models.tiers["ultra"].expected_id
    assert f"<package>\n{PACKAGE}\n</package>" in request["messages"][0]["content"]
    assert record["outcome"] == "ok" and record["answer"]["recognised"] is False
    assert (out / "probe" / "case_k.json").is_file()
    assert (out / "raw" / "probe" / "case_k.json").is_file()
    assert not (tmp_path / "bench").exists()
    [line] = _ledger(tmp_path)
    assert (line["use"], line["phase"]) == ("benchmark", "6")


def test_a_cut_off_probe_is_a_failure_never_parsed(tmp_path: Path, config: Config) -> None:
    gateway, _, source, out = _setup(tmp_path, config, _probe(), finish_reason="length")
    record = run_probe(gateway, config, "k", source_dir=source, out_root=out)
    assert record["outcome"] != "ok" and record["answer"] is None


# --- the baselines ----------------------------------------------------------------------------


def test_baseline_b_writes_under_the_given_root_never_bench_test5(
    tmp_path: Path, config: Config
) -> None:
    gateway, transport, source, out = _setup(tmp_path, config, _hazards())
    record = run_baseline(
        gateway, config, "k", baseline=BASELINE_B, source_dir=source, out_root=out
    )
    [(job, request)] = transport.sent
    assert job == "baseline_plain"
    assert f"<package>\n{PACKAGE}\n</package>" in request["messages"][0]["content"]
    assert "checklist" not in request["messages"][0]["content"].lower()
    assert record["outcome"] == "ok" and record["prompt_version"] == "baseline_plain/v1"
    assert (out / BASELINE_B.folder / "case_k.json").is_file()
    assert (out / "raw" / BASELINE_B.folder / "case_k.json").is_file()
    assert not (tmp_path / "bench").exists()
    [line] = _ledger(tmp_path)
    assert (line["use"], line["phase"]) == ("benchmark", "6")


def test_baseline_b_uses_5as_schema_and_validator(tmp_path: Path, config: Config) -> None:
    out_of_order = _hazards()
    out_of_order["hazards"][0]["rank"] = 2
    gateway, _, source, out = _setup(tmp_path, config, out_of_order)
    record = run_baseline(
        gateway, config, "k", baseline=BASELINE_B, source_dir=source, out_root=out
    )
    assert record["outcome"] != "ok" and record["hazards"] == []


# --- G7: the probe judgement (step 3b) --------------------------------------------------------


def _keys(path: Path) -> Path:
    keys = [
        {
            "case_id": "K",
            "source": "A public investigation report",
            "root_cause": SECRET,
            "match_phrases": [SECRET],
            "component_ids": [SECRET],
        }
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(keys), encoding="utf-8")
    return path


def _probes(out: Path) -> Path:
    (out / "probe").mkdir(parents=True)
    record = {"case": "case_k", "outcome": "ok", "answer": _probe()}
    (out / "probe" / "case_k.json").write_text(json.dumps(record), encoding="utf-8")
    return out / "probe"


def test_the_judgement_reads_only_the_keys_source(tmp_path: Path) -> None:
    rows = judgement_rows(_probes(tmp_path / "out"), _keys(tmp_path / "keys.json"))
    [row] = rows
    assert row.case == "k" and row.source == "A public investigation report"
    assert SECRET not in repr(rows)


def test_the_judgement_csv_is_written_once_for_bhargavi_to_fill(tmp_path: Path) -> None:
    rows = judgement_rows(_probes(tmp_path / "out"), _keys(tmp_path / "keys.json"))
    target = tmp_path / "probe_judgement.csv"
    write_judgement(rows, target)
    with target.open(encoding="utf-8", newline="") as f:
        written = list(csv.DictReader(f))
    assert written == [{"case": "k", "recognised_by_probe": "no", "excluded": "", "reason": ""}]
    with pytest.raises(JudgementRefused, match="exists"):
        write_judgement(rows, target)


def _csv(path: Path, rows: list[dict[str, str]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, ["case", "recognised_by_probe", "excluded", "reason"])
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_a_filled_judgement_is_read(tmp_path: Path) -> None:
    path = _csv(
        tmp_path / "j.csv",
        [
            {"case": "k", "recognised_by_probe": "no", "excluded": "no", "reason": "not named"},
            {"case": "l", "recognised_by_probe": "no", "excluded": "yes", "reason": "site named"},
        ],
    )
    assert read_judgement(path) == {"k": False, "l": True}


@pytest.mark.parametrize(
    "row",
    [
        {"case": "k", "recognised_by_probe": "no", "excluded": "", "reason": ""},
        {"case": "k", "recognised_by_probe": "no", "excluded": "maybe", "reason": "r"},
        {"case": "k", "recognised_by_probe": "no", "excluded": "yes", "reason": ""},
    ],
)
def test_an_unfilled_or_unclear_judgement_row_is_refused(
    tmp_path: Path, row: dict[str, str]
) -> None:
    with pytest.raises(JudgementRefused, match="case k"):
        read_judgement(_csv(tmp_path / "j.csv", [row]))


# --- the scripts ------------------------------------------------------------------------------


def test_the_probe_script_refuses_to_run_outside_a_freeze_checkout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """This checkout is a working branch, not a `phase6-freeze*` tag: no call is made."""
    import probe_heldout

    ledger = tmp_path / "main" / "ledger.jsonl"
    ledger.parent.mkdir()
    ledger.write_text('{"kind": "opening_balance", "cost_usd": 0.1}\n', encoding="utf-8")
    code = probe_heldout.main(
        [
            str(tmp_path / "heldout"),
            "--store",
            str(tmp_path / "guideword-benchmark.db"),
            "--ledger",
            str(ledger),
            "--out",
            str(tmp_path / "out"),
            "--phase",
            "6",
        ],
        transport=None,
    )
    assert code == 1 and "refused" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def test_run_test5a_with_use_benchmark_needs_a_store_and_a_ledger(
    capsys: pytest.CaptureFixture[str],
) -> None:
    import run_test5a

    assert run_test5a.main(["--case", "k", "--use", "benchmark"]) == 1
    assert "--store and --ledger" in capsys.readouterr().err


def test_the_judgement_script_prints_the_source_and_nothing_else_of_the_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import probe_judgement

    probes = _probes(tmp_path / "out")
    keys = _keys(tmp_path / "keys.json")
    target = tmp_path / "probe_judgement.csv"
    assert (
        probe_judgement.main(
            ["--probe-dir", str(probes), "--keys", str(keys), "--csv", str(target)]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "key source: A public investigation report" in out and SECRET not in out
    assert target.is_file()


def test_the_judgement_reads_the_templates_source_object(tmp_path: Path) -> None:
    """`docs/case-template.md` §4 gives `source` as an object (kind, reference, pages)."""
    import re as regex

    text = (Path(__file__).resolve().parents[3] / "docs" / "case-template.md").read_text("utf-8")
    block = regex.search(r"```json\n(.*?)\n```", text.split("## 4. The answer key", 1)[1], regex.S)
    assert block is not None
    key = json.loads(block.group(1)) | {"root_cause": SECRET}
    keys = tmp_path / "keys.json"
    keys.write_text(json.dumps([key]), encoding="utf-8")
    [row] = judgement_rows(_probes(tmp_path / "out"), keys)
    assert row.case == "k" and row.source["kind"] == "public investigation report"
    assert SECRET not in repr(row)
