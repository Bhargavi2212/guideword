"""The four-tier comparison (spec 2.10; plan PR 12b, R9, R27, R35): the same 50 questions from
D–H, each answered by its own specialist on Ultra, Super, Lightning and Nano. Fake transport
only, an injected timer, no network."""

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from guideword.bench.four_tier import (
    SAMPLE_SIZE,
    load_cases,
    run_four_tier,
    sample,
    write_outputs,
)
from guideword.config import Config, load_config
from guideword.gateway.fake import fake_gateway, reply
from guideword.gateway.transport import Reply
from guideword.reference import ReferenceSet, load_reference_set
from guideword.runs.db import make_session_factory
from guideword.schema import ids
from guideword.specialists.routing import agent_for

REPO = Path(__file__).resolve().parents[3]
DEV = REPO / "cases" / "dev"
NOW = datetime(2026, 10, 17, 9, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def ref() -> ReferenceSet:
    return load_reference_set()


@pytest.fixture(scope="module")
def config() -> Config:
    return load_config(global_budget_usd=25.0)


@pytest.fixture(scope="module")
def picked(ref: ReferenceSet) -> list[Any]:
    return sample(load_cases(DEV), ref)


def tier_of(request: dict[str, Any], config: Config) -> str:
    return next(t for t, m in config.models.tiers.items() if m.expected_id == request["model"])


def questions_in(request: dict[str, Any]) -> list[str]:
    import re  # noqa: PLC0415

    match = re.search(
        r"<questions>\s*(.*?)\s*</questions>", request["messages"][0]["content"], re.S
    )
    assert match is not None
    return [q["id"] for q in json.loads(match.group(1))]


def answering(config: Config, broken_tier: str | None = None, billed: bool = False) -> Any:
    """Every tier dismisses its questions as not credible (a valid answer); `broken_tier`
    answers with text that is not the schema. `billed` bills each call at its estimated input
    and its full `max_tokens`, so real spend tracks the gateway's ceiling checks."""

    def script(job: str, request: dict[str, Any]) -> Reply:
        if billed:
            from guideword.gateway.estimate import estimate_cost  # noqa: PLC0415

            prices = config.models.tiers[tier_of(request, config)]
            used = estimate_cost(prices, request["messages"], request.get("tools"), 0)
            tokens = {"input_tokens": used.input_tokens, "output_tokens": request["max_tokens"]}
        else:
            tokens = {}
        if tier_of(request, config) == broken_tier:
            return reply("not an answer", **tokens)
        answers = [
            {"question_id": q, "not_credible": {"reason": "not here"}, "findings": []}
            for q in questions_in(request)
        ]
        return reply({"answers": answers, "added_questions": []}, **tokens)

    return script


def gateway_for(tmp_path: Path, config: Config, script: Any) -> Any:
    sessions = make_session_factory(f"sqlite:///{(tmp_path / 'g.db').as_posix()}")
    return fake_gateway(
        config,
        script,
        sessions=sessions,
        ledger_path=tmp_path / "ledger.jsonl",
        clock=lambda: NOW,
        use="test_5",
    )


class Timer:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        self.t += 0.5
        return self.t


def test_sample_is_the_50_lowest_hashes_and_reproducible(
    picked: list[Any], ref: ReferenceSet
) -> None:
    assert len(picked) == SAMPLE_SIZE
    every = sample(load_cases(DEV), ref, size=10_000)
    ranked = sorted(every, key=lambda s: ids.h([s.plant.plant_id, s.question.id]))
    assert [s.key for s in picked] == [s.key for s in ranked[:SAMPLE_SIZE]]
    again = sample(list(reversed(load_cases(DEV))), ref)
    assert [s.key for s in again] == [s.key for s in picked]
    assert len({s.key for s in picked}) == SAMPLE_SIZE  # case-qualified keys never collide


def test_every_question_is_answered_once_per_tier_by_its_own_agent_in_unmixed_batches(
    tmp_path: Path, config: Config, ref: ReferenceSet, picked: list[Any]
) -> None:
    gateway, transport = gateway_for(tmp_path, config, answering(config))
    result = run_four_tier(gateway, config, ref, picked, cap_usd=5.0, timer=Timer())
    by_key = {s.question.id: s for s in picked}
    seen: dict[str, list[str]] = {t: [] for t in config.models.tiers}
    for _, request in transport.sent:
        if "<questions>" not in request["messages"][0]["content"] or request.get("tools"):
            continue  # a tool request repeats the batch; count the answer call
        tier = tier_of(request, config)
        batch = questions_in(request)
        members = [s for q in batch for s in picked if s.question.id == q]
        assert len({s.case for s in members}) == 1, "a batch mixes cases"
        assert len({agent_for(s.question, {x.id: x for x in s.sections}) for s in members}) == 1
        seen[tier] += batch
    for tier, got in seen.items():
        assert sorted(got) == sorted(s.question.id for s in picked), tier
    assert set(result.tiers) == set(config.models.tiers)
    assert all(t.valid == SAMPLE_SIZE for t in result.tiers.values())
    assert by_key  # the sample is not empty


def test_valid_rate_latency_and_cost_per_tier(
    tmp_path: Path, config: Config, ref: ReferenceSet, picked: list[Any]
) -> None:
    gateway, _ = gateway_for(tmp_path, config, answering(config, broken_tier="nano"))
    result = run_four_tier(gateway, config, ref, picked, cap_usd=5.0, timer=Timer())
    assert result.tiers["nano"].valid == 0 and result.tiers["nano"].valid_rate == 0.0
    assert result.tiers["ultra"].valid_rate == 1.0
    assert all(t.median_latency_s > 0 and t.cost_usd > 0 for t in result.tiers.values())
    assert result.stopped is None


def test_a_refusal_at_the_cap_stops_the_sample_and_is_reported(
    tmp_path: Path, config: Config, ref: ReferenceSet, picked: list[Any]
) -> None:
    gateway, _ = gateway_for(tmp_path, config, answering(config))
    result = run_four_tier(gateway, config, ref, picked, cap_usd=0.0001, timer=Timer())
    assert result.stopped is not None and "cap" in result.stopped
    assert sum(t.answered for t in result.tiers.values()) < SAMPLE_SIZE * len(config.models.tiers)


def test_a_stop_at_the_cap_cuts_every_tier_at_about_the_same_point(
    tmp_path: Path, config: Config, ref: ReferenceSet, picked: list[Any]
) -> None:
    """Groups run with every tier in turn, so no tier is left out by a cap stop."""
    gateway, _ = gateway_for(tmp_path, config, answering(config, billed=True))
    full = run_four_tier(gateway, config, ref, picked, cap_usd=50.0, timer=Timer())
    total = sum(t.cost_usd for t in full.tiers.values())
    (tmp_path / "second").mkdir()
    gateway, _ = gateway_for(tmp_path / "second", config, answering(config, billed=True))
    half = run_four_tier(gateway, config, ref, picked, cap_usd=total / 2, timer=Timer())
    assert half.stopped is not None
    done = [t.answered for t in half.tiers.values()]
    assert min(done) > 0, done


def test_outputs_raw_calls_answers_and_a_blank_score_sheet_that_keeps_scores(
    tmp_path: Path, config: Config, ref: ReferenceSet, picked: list[Any]
) -> None:
    gateway, _ = gateway_for(tmp_path, config, answering(config))
    result = run_four_tier(gateway, config, ref, picked, cap_usd=5.0, timer=Timer())
    root = tmp_path / "test5"
    write_outputs(result, root)
    summary = json.loads((root / "four_tier" / "summary.json").read_text(encoding="utf-8"))
    assert set(summary["tiers"]) == set(config.models.tiers)
    raw = list((root / "raw" / "four_tier").rglob("*.json"))
    assert raw and all("request" in json.loads(p.read_text(encoding="utf-8")) for p in raw)
    answers = json.loads((root / "four_tier" / "answers" / "ultra.json").read_text("utf-8"))
    assert len(answers) == SAMPLE_SIZE and {"key", "question", "answer"} <= set(answers[0])
    sheet = root / "four_tier_scores.csv"
    rows = list(csv.DictReader(sheet.open(encoding="utf-8")))
    assert list(rows[0]) == ["question_key", "tier", "score", "reason"]
    assert len(rows) == SAMPLE_SIZE * len(config.models.tiers)
    assert all(r["score"] == "" for r in rows)
    rows[0]["score"], rows[0]["reason"] = "good", "names the cause"
    with sheet.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["question_key", "tier", "score", "reason"])
        writer.writeheader()
        writer.writerows(rows)
    write_outputs(result, root)
    kept = list(csv.DictReader(sheet.open(encoding="utf-8")))
    assert (kept[0]["score"], kept[0]["reason"]) == ("good", "names the cause")


def test_the_script_runs_every_tier_through_the_gateway_and_writes_the_outputs(
    tmp_path: Path, config: Config, capsys: pytest.CaptureFixture[str]
) -> None:
    import four_tier  # noqa: PLC0415

    from guideword.gateway.fake import FakeTransport, catalog_for  # noqa: PLC0415
    from guideword.gateway.ledgers import LaptopLedger  # noqa: PLC0415
    from guideword.settings import Settings  # noqa: PLC0415

    transport = FakeTransport(answering(config), catalog_for(config))
    code = four_tier.main(
        ["--use", "test_5", "--cap", "5.00"],
        transport=transport,
        config=config,
        settings=Settings(
            _env_file=None,  # type: ignore[call-arg]
            database_url=f"sqlite:///{(tmp_path / 'g.db').as_posix()}",
        ),
        ledger=LaptopLedger(tmp_path / "ledger.jsonl"),
        clock=lambda: NOW,
        timer=Timer(),
        out_root=tmp_path / "test5",
    )
    out = capsys.readouterr().out
    assert code == 0
    assert (tmp_path / "test5" / "four_tier" / "summary.json").exists()
    for tier in config.models.tiers:
        assert f"{tier}: {SAMPLE_SIZE}/{SAMPLE_SIZE} valid" in out
    entries = LaptopLedger(tmp_path / "ledger.jsonl").entries()
    assert entries and {e.use for e in entries} == {"test_5"}
