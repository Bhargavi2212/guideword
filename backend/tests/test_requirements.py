"""Compiled requirements must stay machine-independent (decision D1)."""

import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
COMPILED = sorted(BACKEND.glob("requirements*.txt"))

# file:/// URLs, Windows drive paths and POSIX home paths all tie a pin to one machine.
ABSOLUTE = re.compile(r"file:/|\b[A-Za-z]:[\\/]|(^|\s)/(home|Users|tmp)/")


def test_compiled_files_exist() -> None:
    names = {p.name for p in COMPILED}
    assert names == {"requirements.txt", "requirements-dev.txt"}


@pytest.mark.parametrize("path", COMPILED, ids=lambda p: p.name)
def test_no_absolute_paths(path: Path) -> None:
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        assert not ABSOLUTE.search(line), f"{path.name}:{number} has an absolute path: {line}"


def test_editable_package_is_relative_to_repo_root() -> None:
    lines = (BACKEND / "requirements-dev.txt").read_text(encoding="utf-8").splitlines()
    assert "-e ./backend" in lines
