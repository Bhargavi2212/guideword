"""A writable copy of reference/ so tests can break one table at a time."""

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

REPO_REFERENCE = Path(__file__).resolve().parents[3] / "reference"


@pytest.fixture
def reference_copy(tmp_path: Path) -> Path:
    target = tmp_path / "reference"
    shutil.copytree(REPO_REFERENCE, target)
    return target


Edit = Callable[[str, Callable[[str], str]], None]


@pytest.fixture
def edit_table(reference_copy: Path) -> Edit:
    """Rewrite one table's text (LF, UTF-8) with the given function."""

    def edit(name: str, change: Callable[[str], str]) -> None:
        path = reference_copy / name
        text = path.read_bytes().decode("utf-8")
        path.write_bytes(change(text).encode("utf-8"))

    return edit
