"""The repo tree from specs/phase-0.md 0.0 exists, and held-out material does not."""

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

SPEC_FOLDERS = [
    ".github/workflows",
    "specs",
    "backend/guideword",
    "backend/guideword/schema",
    "backend/guideword/reference",
    "backend/guideword/api",
    "backend/guideword/sections",
    "backend/guideword/questions",
    "backend/guideword/gateway",
    "backend/guideword/orchestrator",
    "backend/guideword/specialists",
    "backend/guideword/tools",
    "backend/guideword/ranking",
    "backend/guideword/runs",
    "backend/guideword/lopa",
    "backend/guideword/connector",
    "backend/guideword/export",
    "backend/guideword/simulator",
    "backend/guideword/importers",
    "backend/guideword/bench",
    "backend/tests",
    "backend/tests/schema",
    "backend/tests/reference",
    "backend/tests/cases",
    "backend/tests/contract",
    "frontend",
    "reference",
    "cases/dev",
    "cases/dev/keys",
    "cases/dev/source",
    "cases/demo",
    "cases/demo/recorded",
    "prompts",
    "config",
    "contract",
    "contract/schemas",
    "contract/fixtures",
    "scripts",
    "scripts/hooks",
    "budget",
    "docs",
    "docs/smoke",
    "bench",
    "bench/replay",
]


@pytest.mark.parametrize("folder", SPEC_FOLDERS)
def test_every_spec_folder_exists(folder: str) -> None:
    assert (REPO / folder).is_dir(), f"missing folder from the spec 0.0 tree: {folder}"


@pytest.mark.parametrize(
    "package",
    [f for f in SPEC_FOLDERS if f.startswith("backend/guideword")],
)
def test_every_package_has_init(package: str) -> None:
    assert (REPO / package / "__init__.py").is_file()


def test_the_held_out_benchmark_is_published() -> None:
    # published after G3 (spec 6.6); bench/test_heldout_published.py checks every file's seal
    assert (REPO / "cases" / "heldout" / "SEALS.txt").is_file()
    assert (REPO / "bench" / "heldout" / "results.md").is_file()
