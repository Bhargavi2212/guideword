"""The precedent index loader (Phase 4 spec 4.2; plan PR 3, Q5, G23).

Cowork wrote `reference/precedent_index.csv` from CSB's public list. Per CLAUDE.md §5 its rows
are never opened here: every test below runs on synthetic rows, and the real file is only
loaded through the loader (header, row count, version).
"""

import shutil
from pathlib import Path

import pytest

from guideword.reference import load_reference_set
from guideword.reference.loader import DEFAULT_REFERENCE_DIR, ReferenceTableError
from guideword.reference.precedents import (
    PRECEDENT_HEADER,
    PRECEDENT_INDEX,
    load_precedent_index,
)

SYNTHETIC = Path(__file__).resolve().parent / "fixtures" / "precedent_index_synthetic.csv"
SPEC_HEADER = (
    "id,title,date,country,company,location,chemicals,equipment_types,mechanism_keywords,"
    "summary,url,source"
)


def _dir_with(tmp_path: Path, text: str) -> Path:
    (tmp_path / PRECEDENT_INDEX).write_text(text, encoding="utf-8", newline="\n")
    return tmp_path


def _synthetic_text() -> str:
    return SYNTHETIC.read_text(encoding="utf-8")


def _rows_replaced(old: str, new: str) -> str:
    text = _synthetic_text()
    assert text.count(old) == 1
    return text.replace(old, new)


def test_index_header_is_frozen() -> None:
    assert ",".join(PRECEDENT_HEADER) == SPEC_HEADER


def test_synthetic_rows_load_with_their_lists_split(tmp_path: Path) -> None:
    shutil.copy(SYNTHETIC, tmp_path / PRECEDENT_INDEX)
    index = load_precedent_index(tmp_path)
    assert [row.id for row in index.rows] == ["P-0001", "P-0002", "P-0003", "P-0004"]
    first = index.rows[0]
    assert first.chemicals == ("propane", "butane")
    assert first.equipment_types == ("heat exchanger", "reboiler")
    # a title-only row: no summary and no keywords, still loaded
    assert index.rows[3].summary == ""
    assert index.rows[3].mechanism_keywords == ()
    assert len(index.version) == 64


def test_every_index_row_has_a_url_and_a_source(tmp_path: Path) -> None:
    no_source = _rows_replaced("P-0002,synthetic test row", "P-0002,")
    with pytest.raises(ReferenceTableError, match="row 3"):
        load_precedent_index(_dir_with(tmp_path, no_source))
    no_url = _rows_replaced("https://precedents.mock.invalid/P-0003", "")
    with pytest.raises(ReferenceTableError, match="row 4"):
        load_precedent_index(_dir_with(tmp_path, no_url))
    http = _rows_replaced("https://precedents.mock.invalid/P-0003", "http://x.invalid/3")
    with pytest.raises(ReferenceTableError, match="row 4"):
        load_precedent_index(_dir_with(tmp_path, http))


def test_index_ids_are_unique(tmp_path: Path) -> None:
    repeated = _rows_replaced("P-0003,Example", "P-0001,Example")
    with pytest.raises(ReferenceTableError, match="repeated"):
        load_precedent_index(_dir_with(tmp_path, repeated))


def test_an_index_id_may_not_be_none_or_hold_a_colon(tmp_path: Path) -> None:
    """`none` is the no-precedent key, and `:` would break the evidence ID (plan G23)."""
    for bad in ("none", "P:3"):
        text = _rows_replaced("P-0003,Example", f"{bad},Example")
        with pytest.raises(ReferenceTableError):
            load_precedent_index(_dir_with(tmp_path, text))


def test_the_index_header_and_line_endings_are_checked(tmp_path: Path) -> None:
    wrong = _synthetic_text().replace("mechanism_keywords", "keywords", 1)
    with pytest.raises(ReferenceTableError, match="frozen header"):
        load_precedent_index(_dir_with(tmp_path, wrong))
    (tmp_path / PRECEDENT_INDEX).write_bytes(_synthetic_text().replace("\n", "\r\n").encode())
    with pytest.raises(ReferenceTableError, match="carriage return"):
        load_precedent_index(tmp_path)


def test_the_index_is_outside_reference_versions() -> None:
    """Loading it never moves a run ID: the run's reference versions don't include it (P4-9)."""
    ref = load_reference_set()
    assert PRECEDENT_INDEX not in ref.versions
    load_precedent_index()
    assert PRECEDENT_INDEX not in load_reference_set().versions


def test_precedent_index_loads_when_present() -> None:
    """Cowork's file, through the loader only: its header is frozen and its 125 rows load."""
    assert (DEFAULT_REFERENCE_DIR / PRECEDENT_INDEX).is_file()
    index = load_precedent_index()
    assert len(index.rows) == 125
    assert len({row.id for row in index.rows}) == 125
