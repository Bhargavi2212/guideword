"""The published held-out benchmark (Phase 6 spec 6.6, after G3).

The cases, keys and plant files the benchmark ran on live under `cases/heldout/`, byte for byte
as sealed on 2026-10-14 (`SEALS.txt`, committed early as `bench/heldout-seals.txt`) and frozen
on 2026-10-28 (`bench/heldout-frozen.txt`). These tests fail if any published file differs from
its seal or its frozen hash, so a judge can trust the files they rerun.
"""

from pathlib import Path

from guideword.bench.heldout import SEALS_FILE, check_seals, frozen_lines

REPO = Path(__file__).resolve().parents[3]
CASES = REPO / "cases" / "heldout"
SEALED = 16  # 8 packages and 8 keys


def test_every_published_case_file_matches_the_seals() -> None:
    check = check_seals(CASES)
    assert check.passed, (check.missing, check.unlisted, check.mismatched, check.bad_lines)
    assert (check.listed, check.ok) == (SEALED, SEALED)


def test_the_published_seals_file_is_the_one_committed_before_the_runs() -> None:
    published = (CASES / SEALS_FILE).read_bytes()
    assert published == (REPO / "bench" / "heldout-seals.txt").read_bytes()


def test_every_published_plant_file_matches_its_frozen_hash() -> None:
    frozen = (REPO / "bench" / "heldout-frozen.txt").read_text(encoding="utf-8")
    paths = [line.split("  ", 1)[1] for line in frozen.splitlines() if line.strip()]
    assert paths, "no frozen plant files"
    assert frozen_lines(CASES, paths) == frozen


def test_the_run_records_are_published_and_no_longer_ignored() -> None:
    assert (REPO / "bench" / "heldout" / "results.md").is_file()
    assert (REPO / "bench" / "heldout" / "case_k" / "shortlist.json").is_file()
    assert (REPO / "bench" / "heldout-post" / "case_q" / "shortlist.json").is_file()
    ignored = (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "bench/heldout/" not in ignored
