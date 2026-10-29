"""The held-out runner's loop (Phase 6 spec 6.4, P6-6 to P6-8; plan G13; acceptance 2). The
three configurations are stand-ins that record what they were asked: what's under test is the
order, the skipping, the stop rule and the runs file. The Guideword configuration itself is
tested on a fake run in `tests/replay/test_benchmark_guideword.py`."""

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from guideword.bench.freeze import FreezeInfo
from guideword.bench.runner import (
    CONFIGS,
    NOT_CONVERTED_FILE,
    Case,
    RunnerRefused,
    benchmark_remaining,
    check_frozen,
    converted_cases,
    find_cases,
    read_lines,
    run_benchmark,
)

FREEZE = FreezeInfo("phase6-freeze", "a" * 40)
STOP = 1.75


def _folder(tmp_path: Path, letters: str = "klmn") -> Path:
    folder = tmp_path / "heldout"
    (folder / "plants").mkdir(parents=True)
    for x in letters:
        (folder / f"case_{x}_unit.md").write_text(f"package {x}", encoding="utf-8")
        (folder / "plants" / f"case_{x}.json").write_text(
            f'{{"plant_id": "{x}"}}', encoding="utf-8"
        )
    return folder


class Stubs:
    """Three configurations that log their calls; Guideword marks a run as started."""

    def __init__(self, cost: float = 1.0, crash_on: str | None = None) -> None:
        self.calls: list[tuple[str, str, str | None]] = []
        self.cost = cost
        self.crash_on = crash_on

    def configs(self) -> dict[str, Callable[..., dict[str, Any]]]:
        def make(name: str) -> Callable[..., dict[str, Any]]:
            def run(case: Case, started: str | None, mark: Callable[[str], None]) -> dict[str, Any]:
                self.calls.append((case.letter, name, started))
                if name == "guideword":
                    if started is None:
                        mark(f"run:{case.letter}")
                    if self.crash_on == case.letter:
                        raise RuntimeError("crashed while driving")
                return {"status": "ok", "cost_usd": self.cost}

            return run

        return {name: make(name) for name in CONFIGS}


def _run(
    tmp_path: Path,
    stubs: Stubs,
    judgement: dict[str, bool],
    remaining: Callable[[], float] = lambda: 5.19,
) -> Any:
    folder = tmp_path / "heldout"
    return run_benchmark(
        find_cases(folder),
        judgement=judgement,
        configs=stubs.configs(),
        lines_path=tmp_path / "out" / "runs.jsonl",
        remaining=remaining,
        stop_below_usd=STOP,
        freeze=FREEZE,
    )


ALL = {"k": False, "l": False, "m": False, "n": False}


def test_cases_are_found_in_letter_order_with_their_package_and_plant(tmp_path: Path) -> None:
    folder = _folder(tmp_path, "nkm")
    cases = find_cases(folder)
    assert [c.letter for c in cases] == ["k", "m", "n"]
    assert cases[0].package.name == "case_k_unit.md" and cases[0].plant.name == "case_k.json"


def test_a_case_without_a_plant_file_is_refused(tmp_path: Path) -> None:
    folder = _folder(tmp_path, "kl")
    (folder / "plants" / "case_l.json").unlink()
    with pytest.raises(RunnerRefused, match="l"):
        find_cases(folder)


def test_cases_run_in_letter_order_a_then_b_then_guideword(tmp_path: Path) -> None:
    _folder(tmp_path, "lk")
    stubs = Stubs()
    summary = _run(tmp_path, stubs, {"k": False, "l": False})
    assert [(c, n) for c, n, _ in stubs.calls] == [
        ("k", "baseline_a"),
        ("k", "baseline_b"),
        ("k", "guideword"),
        ("l", "baseline_a"),
        ("l", "baseline_b"),
        ("l", "guideword"),
    ]
    assert summary.run == ["k", "l"]


def test_excluded_cases_are_skipped(tmp_path: Path) -> None:
    _folder(tmp_path)
    stubs = Stubs()
    summary = _run(tmp_path, stubs, ALL | {"l": True})
    assert "l" not in {c for c, _, _ in stubs.calls}
    assert summary.excluded == ["l"]


def test_a_case_with_no_probe_row_is_refused_before_any_call(tmp_path: Path) -> None:
    _folder(tmp_path)
    stubs = Stubs()
    with pytest.raises(RunnerRefused, match="m"):
        _run(tmp_path, stubs, {"k": False, "l": False, "n": False})
    assert stubs.calls == []


def test_the_stop_rule_stops_before_a_case_and_lists_the_unrun_ones(tmp_path: Path) -> None:
    _folder(tmp_path)
    stubs = Stubs()
    left = iter([5.19, 3.50, 1.74])
    summary = _run(tmp_path, stubs, ALL | {"n": True}, remaining=lambda: next(left))
    assert summary.run == ["k", "l"]
    assert summary.unrun == ["m"]  # n is excluded, so not "unrun"
    assert summary.stopped_with_usd == pytest.approx(1.74)
    assert "m" not in {c for c, _, _ in stubs.calls}


def test_exactly_at_the_threshold_a_case_still_starts(tmp_path: Path) -> None:
    _folder(tmp_path, "k")
    summary = _run(tmp_path, Stubs(), {"k": False}, remaining=lambda: STOP)
    assert summary.run == ["k"]


def test_a_started_line_is_written_before_the_run_and_read_back_after_a_crash(
    tmp_path: Path,
) -> None:
    _folder(tmp_path, "k")
    with pytest.raises(RuntimeError, match="crashed"):
        _run(tmp_path, Stubs(crash_on="k"), {"k": False})
    lines = read_lines(tmp_path / "out" / "runs.jsonl")
    assert [(x["config"], x["state"]) for x in lines] == [
        ("baseline_a", "done"),
        ("baseline_b", "done"),
        ("guideword", "started"),
    ]
    # the next start resumes the same run, and never asks for the baselines again
    again = Stubs()
    summary = _run(tmp_path, again, {"k": False}, remaining=lambda: 0.0)
    assert again.calls == [("k", "guideword", "run:k")]
    assert summary.run == ["k"]  # a started case is finished whatever the stop rule says


def test_a_case_with_every_config_done_is_never_run_again(tmp_path: Path) -> None:
    _folder(tmp_path, "k")
    _run(tmp_path, Stubs(), {"k": False})
    again = Stubs()
    summary = _run(tmp_path, again, {"k": False})
    assert again.calls == [] and summary.already_done == ["k"]


def test_every_line_records_the_freeze_tag_and_commit(tmp_path: Path) -> None:
    _folder(tmp_path, "k")
    _run(tmp_path, Stubs(), {"k": False})
    for line in read_lines(tmp_path / "out" / "runs.jsonl"):
        assert (line["freeze_tag"], line["freeze_commit"]) == (FREEZE.tag, FREEZE.commit)


def test_remaining_counts_only_the_benchmark_use() -> None:
    class Entry:
        def __init__(self, use: str, cost: float) -> None:
            self.use, self.cost_usd = use, cost

    entries = [Entry("benchmark", 1.0), Entry("development", 3.0), Entry("benchmark", 0.5)]
    assert benchmark_remaining(entries, 5.19) == pytest.approx(3.69)


# --- G13: the plant files are the frozen ones -------------------------------------------------


def _frozen(folder: Path, tmp_path: Path) -> Path:
    lines = [
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(folder).as_posix()}\n"
        for p in sorted((folder / "plants").glob("*.json"))
    ]
    path = tmp_path / "heldout-frozen.txt"
    path.write_text("".join(lines), encoding="utf-8")
    return path


def test_frozen_plant_files_pass(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    check_frozen(folder, find_cases(folder), _frozen(folder, tmp_path))


def test_a_plant_file_changed_after_freezing_is_refused_naming_the_file(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    frozen = _frozen(folder, tmp_path)
    plant = folder / "plants" / "case_m.json"
    plant.write_text(json.dumps({"plant_id": "m", "edited": True}), encoding="utf-8")
    with pytest.raises(RunnerRefused, match="plants/case_m.json"):
        check_frozen(folder, find_cases(folder), frozen)


def test_a_plant_file_missing_from_the_frozen_list_is_refused(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    frozen = _frozen(folder, tmp_path)
    (folder / "case_p_unit.md").write_text("package p", encoding="utf-8")
    (folder / "plants" / "case_p.json").write_text("{}", encoding="utf-8")
    with pytest.raises(RunnerRefused, match="case_p.json"):
        check_frozen(folder, find_cases(folder), frozen)


# --- the scripts ------------------------------------------------------------------------------


def _ledger(tmp_path: Path) -> Path:
    path = tmp_path / "main" / "ledger.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"kind": "opening_balance", "cost_usd": 0.1}\n', encoding="utf-8")
    return path


def test_run_benchmark_refuses_outside_a_freeze_checkout_and_makes_no_call(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """This checkout is a working branch, not a `phase6-freeze*` tag."""
    import run_benchmark

    folder = _folder(tmp_path)
    code = run_benchmark.main(
        [
            str(folder),
            "--store",
            str(tmp_path / "guideword-benchmark.db"),
            "--ledger",
            str(_ledger(tmp_path)),
            "--frozen",
            str(_frozen(folder, tmp_path)),
            "--judgement",
            str(tmp_path / "j.csv"),
            "--out",
            str(tmp_path / "out"),
            "--phase",
            "6",
        ]
    )
    assert code == 1 and "refused" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("store", ["guideword.db", "guideword-demo.db"])
def test_run_benchmark_refuses_the_source_and_demo_stores(
    tmp_path: Path, store: str, capsys: pytest.CaptureFixture[str]
) -> None:
    import run_benchmark

    folder = _folder(tmp_path)
    args = [str(folder), "--store", str(tmp_path / store), "--ledger", str(_ledger(tmp_path))]
    args += ["--frozen", str(_frozen(folder, tmp_path)), "--judgement", str(tmp_path / "j.csv")]
    args += ["--out", str(tmp_path / "out"), "--phase", "6"]
    assert run_benchmark.main(args) == 1
    assert store in capsys.readouterr().err


def test_run_case_with_use_benchmark_needs_a_store_and_a_ledger(
    capsys: pytest.CaptureFixture[str],
) -> None:
    import run_case

    assert run_case.main(["x.json", "--use", "benchmark"]) == 1
    assert "--store and --ledger" in capsys.readouterr().err


# --- a subset frozen (decisions 2026-10-28): a case with no frozen plant file is not run ------


def _frozen_only(folder: Path, tmp_path: Path, letters: str) -> Path:
    lines = [
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(folder).as_posix()}\n"
        for p in sorted((folder / "plants").glob("*.json"))
        if p.stem[-1] in letters
    ]
    path = tmp_path / "heldout-frozen.txt"
    path.write_text("".join(lines), encoding="utf-8")
    return path


def test_a_case_with_no_frozen_plant_file_is_not_converted_never_an_error(
    tmp_path: Path,
) -> None:
    """k and l are frozen; m has a plant file that was never frozen; n has none."""
    folder = _folder(tmp_path, "klmn")
    (folder / "plants" / "case_n.json").unlink()
    found = converted_cases(folder, _frozen_only(folder, tmp_path, "kl"))
    assert [c.letter for c in found.cases] == ["k", "l"]
    assert found.not_converted == ["m", "n"]


def test_a_frozen_plant_file_that_is_missing_is_refused(tmp_path: Path) -> None:
    folder = _folder(tmp_path, "kl")
    frozen = _frozen_only(folder, tmp_path, "kl")
    (folder / "plants" / "case_l.json").unlink()
    with pytest.raises(RunnerRefused, match="case_l.json"):
        converted_cases(folder, frozen)


def test_a_frozen_plant_file_changed_since_is_still_refused(tmp_path: Path) -> None:
    folder = _folder(tmp_path, "kl")
    frozen = _frozen_only(folder, tmp_path, "kl")
    (folder / "plants" / "case_k.json").write_text('{"plant_id": "edited"}', encoding="utf-8")
    with pytest.raises(RunnerRefused, match="plants/case_k.json"):
        converted_cases(folder, frozen)


def test_a_plant_file_with_no_package_is_still_refused(tmp_path: Path) -> None:
    folder = _folder(tmp_path, "kl")
    (folder / "case_l_unit.md").unlink()
    with pytest.raises(RunnerRefused, match="l"):
        converted_cases(folder, _frozen_only(folder, tmp_path, "kl"))


def test_not_converted_cases_are_listed_never_run_and_need_no_probe_row(
    tmp_path: Path,
) -> None:
    folder = _folder(tmp_path, "klmn")
    found = converted_cases(folder, _frozen_only(folder, tmp_path, "kl"))
    stubs = Stubs()
    out = tmp_path / "out"
    summary = run_benchmark(
        found.cases,
        not_converted=found.not_converted,
        judgement={"k": False, "l": False},
        configs=stubs.configs(),
        lines_path=out / "runs.jsonl",
        remaining=lambda: 5.19,
        stop_below_usd=STOP,
        freeze=FREEZE,
    )
    assert summary.run == ["k", "l"] and summary.not_converted == ["m", "n"]
    assert {letter for letter, _, _ in stubs.calls} == {"k", "l"}
    assert {x["case"] for x in read_lines(out / "runs.jsonl")} == {"k", "l"}
    record = json.loads((out / NOT_CONVERTED_FILE).read_text(encoding="utf-8"))
    assert record == {
        "cases": ["m", "n"],
        "freeze_tag": FREEZE.tag,
        "freeze_commit": FREEZE.commit,
    }


def test_the_stop_rule_never_lists_a_not_converted_case(tmp_path: Path) -> None:
    folder = _folder(tmp_path, "klmn")
    found = converted_cases(folder, _frozen_only(folder, tmp_path, "kl"))
    summary = run_benchmark(
        found.cases,
        not_converted=found.not_converted,
        judgement={"k": False, "l": False},
        configs=Stubs().configs(),
        lines_path=tmp_path / "out" / "runs.jsonl",
        remaining=lambda: 1.0,
        stop_below_usd=STOP,
        freeze=FREEZE,
    )
    assert summary.unrun == ["k", "l"] and summary.not_converted == ["m", "n"]


def test_a_later_start_rewrites_the_not_converted_record(tmp_path: Path) -> None:
    """If the probe excludes enough cases, the next one is converted and frozen before the runs:
    the record names only what is still unconverted."""
    folder = _folder(tmp_path, "klmn")
    out = tmp_path / "out"
    for frozen_letters in ("kl", "klm"):
        found = converted_cases(folder, _frozen_only(folder, tmp_path, frozen_letters))
        run_benchmark(
            found.cases,
            not_converted=found.not_converted,
            judgement=dict.fromkeys("klm", False),
            configs=Stubs().configs(),
            lines_path=out / "runs.jsonl",
            remaining=lambda: 5.19,
            stop_below_usd=STOP,
            freeze=FREEZE,
        )
    assert json.loads((out / NOT_CONVERTED_FILE).read_text("utf-8"))["cases"] == ["n"]
    assert {x["case"] for x in read_lines(out / "runs.jsonl")} == {"k", "l", "m"}
