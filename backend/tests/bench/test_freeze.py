"""The checks every benchmark script makes before a call (Phase 6 spec P6-2, 6.4; plan G1,
G2a-G2c). Each runs on a throwaway git repo in `tmp_path`."""

import json
import subprocess
from pathlib import Path

import pytest

from guideword.bench.freeze import (
    FreezeRefused,
    check_checkout,
    check_ledger,
    check_store,
)

GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]


def _git(repo: Path, *args: str) -> None:
    subprocess.run([*GIT, *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repo with a backend package and a script, committed and tagged `phase6-freeze`."""
    root = tmp_path / "freeze"
    (root / "backend" / "guideword").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "backend" / "guideword" / "__init__.py").write_text("", encoding="utf-8")
    (root / "scripts" / "run_benchmark.py").write_text("", encoding="utf-8")
    (root / ".gitignore").write_text("*.db\nbudget/\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "freeze")
    _git(root, "tag", "phase6-freeze")
    return root


def _check(root: Path) -> object:
    return check_checkout(
        root,
        package_file=root / "backend" / "guideword" / "__init__.py",
        script_file=root / "scripts" / "run_benchmark.py",
    )


def test_a_clean_checkout_at_the_tag_passes_and_names_tag_and_commit(repo: Path) -> None:
    info = _check(repo)
    assert info.tag == "phase6-freeze"  # type: ignore[attr-defined]
    assert len(info.commit) == 40  # type: ignore[attr-defined]


def test_a_later_freeze_tag_passes(repo: Path) -> None:
    (repo / "scripts" / "fix.py").write_text("", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "fix")
    _git(repo, "tag", "phase6-freeze-2")
    assert _check(repo).tag == "phase6-freeze-2"  # type: ignore[attr-defined]


def test_a_dirty_tree_is_refused(repo: Path) -> None:
    (repo / "scripts" / "run_benchmark.py").write_text("changed", encoding="utf-8")
    with pytest.raises(FreezeRefused, match="clean"):
        _check(repo)


def test_an_ignored_file_doesnt_make_the_tree_dirty(repo: Path) -> None:
    (repo / "guideword-benchmark.db").write_bytes(b"store")
    _check(repo)


def test_an_untagged_commit_is_refused(repo: Path) -> None:
    (repo / "scripts" / "later.py").write_text("", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "later")
    with pytest.raises(FreezeRefused, match="phase6-freeze"):
        _check(repo)


def test_another_tag_is_refused(repo: Path) -> None:
    (repo / "scripts" / "later.py").write_text("", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "later")
    _git(repo, "tag", "contract-v1.11")
    with pytest.raises(FreezeRefused, match="phase6-freeze"):
        _check(repo)


def test_a_package_imported_from_outside_the_checkout_is_refused(
    repo: Path, tmp_path: Path
) -> None:
    other = tmp_path / "main" / "backend" / "guideword" / "__init__.py"
    with pytest.raises(FreezeRefused, match="PYTHONPATH"):
        check_checkout(repo, package_file=other, script_file=repo / "scripts" / "run_benchmark.py")


def test_a_script_from_outside_the_checkout_is_refused(repo: Path, tmp_path: Path) -> None:
    with pytest.raises(FreezeRefused, match="script"):
        check_checkout(
            repo,
            package_file=repo / "backend" / "guideword" / "__init__.py",
            script_file=tmp_path / "elsewhere.py",
        )


def test_a_folder_that_isnt_a_git_checkout_is_refused(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(FreezeRefused):
        check_checkout(plain, package_file=plain / "x.py", script_file=plain / "y.py")


# --- the ledger and the store ------------------------------------------------------------------


def _ledger(path: Path, *, opening: bool = True) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [{"kind": "opening_balance", "cost_usd": 0.1}] if opening else []
    lines.append({"kind": "model", "cost_usd": 0.01})
    path.write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
    return path


def test_the_main_ledger_passes(repo: Path, tmp_path: Path) -> None:
    check_ledger(_ledger(tmp_path / "main" / "budget" / "ledger.jsonl"), repo)


def test_a_ledger_inside_the_freeze_checkout_is_refused(repo: Path) -> None:
    with pytest.raises(FreezeRefused, match="main checkout"):
        check_ledger(_ledger(repo / "budget" / "ledger.jsonl"), repo)


def test_a_ledger_without_an_opening_balance_is_refused(repo: Path, tmp_path: Path) -> None:
    with pytest.raises(FreezeRefused, match="opening balance"):
        check_ledger(_ledger(tmp_path / "main" / "ledger.jsonl", opening=False), repo)


def test_a_missing_ledger_is_refused(repo: Path, tmp_path: Path) -> None:
    with pytest.raises(FreezeRefused, match="no ledger"):
        check_ledger(tmp_path / "nowhere" / "ledger.jsonl", repo)


@pytest.mark.parametrize("name", ["guideword.db", "guideword-demo.db"])
def test_the_source_and_demo_stores_are_refused_by_name(tmp_path: Path, name: str) -> None:
    with pytest.raises(FreezeRefused, match=name):
        check_store(tmp_path / name)


def test_the_benchmark_store_passes(tmp_path: Path) -> None:
    check_store(tmp_path / "guideword-benchmark.db")


def test_require_benchmark_makes_every_check(repo: Path, tmp_path: Path) -> None:
    from guideword.bench.freeze import require_benchmark

    ledger = _ledger(tmp_path / "main" / "budget" / "ledger.jsonl")
    files = {
        "package_file": repo / "backend" / "guideword" / "__init__.py",
        "script_file": repo / "scripts" / "run_benchmark.py",
    }
    info = require_benchmark(
        repo, store=tmp_path / "guideword-benchmark.db", ledger=ledger, **files
    )
    assert info.tag == "phase6-freeze"
    with pytest.raises(FreezeRefused, match="guideword.db"):
        require_benchmark(repo, store=tmp_path / "guideword.db", ledger=ledger, **files)
    with pytest.raises(FreezeRefused, match="main checkout"):
        require_benchmark(
            repo,
            store=tmp_path / "guideword-benchmark.db",
            ledger=_ledger(repo / "budget" / "ledger.jsonl"),
            **files,
        )


# --- check_freeze_diff (plan G2) ---------------------------------------------------------------


def _later_tag(repo: Path, path: str, tag: str = "phase6-freeze-2") -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("changed", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", f"change {path}")
    _git(repo, "tag", tag)


@pytest.mark.parametrize(
    "path",
    [
        "backend/guideword/bench/runner.py",
        "scripts/run_benchmark.py",
        # the tooling's own tests and the decisions log change nothing a run executes
        "backend/tests/bench/test_runner.py",
        "docs/decisions.md",
        # the frozen plant files' hashes: the freeze's own output, read from the main checkout
        "bench/heldout-frozen.txt",
    ],
)
def test_a_later_tag_changing_only_bench_and_scripts_passes(repo: Path, path: str) -> None:
    import check_freeze_diff

    _later_tag(repo, path)
    assert check_freeze_diff.main(["phase6-freeze-2"], root=repo) == 0


@pytest.mark.parametrize(
    "path",
    [
        "backend/guideword/api/app.py",
        "backend/guideword/export/xlsx.py",
        "backend/guideword/runs/case.py",
        "prompts/probe/v1.md",
        "config/routing.yaml",
        "backend/guideword/review/text_check.py",
        "frontend/src/screens/Shortlist.tsx",
        "reference/causes.csv",
        "bench/test5/results.md",
        "bench/heldout-seals.txt",
    ],
)
def test_a_later_tag_changing_anything_else_is_refused(
    repo: Path, path: str, capsys: pytest.CaptureFixture[str]
) -> None:
    import check_freeze_diff

    _later_tag(repo, path)
    assert check_freeze_diff.main(["phase6-freeze-2"], root=repo) == 1
    assert path in capsys.readouterr().out


def test_a_tag_not_named_phase6_freeze_is_refused(repo: Path) -> None:
    import check_freeze_diff

    _later_tag(repo, "scripts/x.py", tag="fix-1")
    assert check_freeze_diff.main(["fix-1"], root=repo) == 1
