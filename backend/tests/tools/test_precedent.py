"""Precedent search by code: block terms, BM25 and the code-built query (Phase 4 spec 4.3;
plan PR 3, Q17, G20). Synthetic rows only (CLAUDE.md §5)."""

import shutil
from pathlib import Path

import pytest

from guideword.reference import load_reference_set
from guideword.reference.precedents import PRECEDENT_INDEX, PrecedentRow, load_precedent_index
from guideword.schema import ids
from guideword.schema.enums import (
    Adequacy,
    Confidence,
    FailingComponentType,
    SectionKind,
    SectionType,
    Tier,
)
from guideword.schema.plant import Plant
from guideword.schema.records import Finding, Section
from guideword.tools.precedent import (
    block_list_for,
    blocked,
    bm25,
    load_block_terms,
    query_for,
    row_texts,
    tokens,
)

ROOT = Path(__file__).resolve().parents[3]
SYNTHETIC = ROOT / "backend" / "tests" / "reference" / "fixtures" / "precedent_index_synthetic.csv"
EXAMPLE = ROOT / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
RUN = "run:test"


@pytest.fixture
def rows(tmp_path: Path) -> tuple[PrecedentRow, ...]:
    shutil.copy(SYNTHETIC, tmp_path / PRECEDENT_INDEX)
    return load_precedent_index(tmp_path).rows


# --- block terms: whole word or phrase, case-insensitive (Q17) -----------------------------------


def test_ea_425b_is_blocked_by_its_own_term() -> None:
    assert blocked(["Reboiler EA-425B ruptured"], ("EA-425B",))
    assert blocked(["reboiler ea-425b ruptured"], ("EA-425B",))
    # \bEA-425\b does not match EA-425B: the list names each reboiler (Cowork's fix)
    assert not blocked(["Reboiler EA-425B ruptured"], ("EA-425",))


def test_upcast_is_not_blocked_by_pca() -> None:
    assert not blocked(["the upcast shaft"], ("PCA",))


def test_pca_mill_is_blocked_by_pca() -> None:
    assert blocked(["Explosion at the PCA mill"], ("PCA",))
    assert blocked(["explosion at the pca mill"], ("PCA",))


def test_a_phrase_term_matches_across_its_words_only_whole() -> None:
    terms = ("propylene fractionator",)
    assert blocked(["Fire at a Propylene Fractionator unit"], terms)
    assert not blocked(["propylene in the fractionator"], terms)
    assert not blocked(["propylene fractionators"], terms)


def test_a_block_term_removes_a_row_by_any_field_or_url(rows: tuple[PrecedentRow, ...]) -> None:
    by_id = {row.id: row for row in rows}
    assert blocked(row_texts(by_id["P-0001"]), ("Mocktown",))  # location
    assert blocked(row_texts(by_id["P-0001"]), ("butane",))  # chemicals
    assert blocked(row_texts(by_id["P-0002"]), ("silo",))  # equipment types
    assert blocked(row_texts(by_id["P-0003"]), ("transmitter",))  # summary
    assert blocked(row_texts(by_id["P-0004"]), ("P-0004",))  # the URL
    assert not blocked(row_texts(by_id["P-0002"]), ("Mocktown",))


def test_block_terms_load_one_per_line_with_comments(tmp_path: Path) -> None:
    path = tmp_path / "x.block.txt"
    path.write_text("# a comment\nWilliams\n\n  Geismar  \nEA-425B\n", encoding="utf-8")
    terms, version = load_block_terms(path)
    assert terms == ("Williams", "Geismar", "EA-425B")
    assert len(version) == 64


def test_the_block_list_is_found_by_plant_id(tmp_path: Path) -> None:
    (tmp_path / "demo").mkdir()
    (tmp_path / "dev").mkdir()
    (tmp_path / "demo" / "mock_plant.block.txt").write_text("Mocktown\n", encoding="utf-8")
    (tmp_path / "dev" / "case_x.block.txt").write_text("Sampleville\n", encoding="utf-8")
    demo = block_list_for("mock_plant", tmp_path)
    assert demo is not None and demo.terms == ("Mocktown",)
    dev = block_list_for("case_x", tmp_path)
    assert dev is not None and dev.terms == ("Sampleville",)
    assert block_list_for("uploaded_plant", tmp_path) is None


def test_the_wg_block_list_is_found_in_the_repo() -> None:
    found = block_list_for("williams_geismar")
    assert found is not None
    assert {"EA-425A", "EA-425B", "Geismar"} <= set(found.terms)


def test_a_plant_id_that_is_not_an_object_id_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        block_list_for("../secrets", tmp_path)


# --- BM25 ----------------------------------------------------------------------------------------


def test_bm25_ranks_by_terms_and_breaks_ties_by_id(rows: tuple[PrecedentRow, ...]) -> None:
    ranked = bm25(rows, "isolated reboiler heating overpressure propane", 5)
    assert [row.id for row, _ in ranked][0] == "P-0001"
    assert all(score > 0 for _, score in ranked)
    # a row sharing no term is left out
    assert "P-0004" not in [row.id for row, _ in ranked]
    # identical rows tie on score: the lower ID comes first
    twins = [rows[1], rows[1].model_copy(update={"id": "P-0000"})]
    assert [row.id for row, _ in bm25(twins, "dust silo", 5)] == ["P-0000", "P-0002"]


def test_bm25_keeps_the_top_k_and_is_deterministic(rows: tuple[PrecedentRow, ...]) -> None:
    query = "tank level dust reboiler"
    assert len(bm25(rows, query, 2)) == 2
    assert bm25(rows, query, 5) == bm25(rows, query, 5)


# --- the query is built by code from the line only -----------------------------------------------


def _finding(question: str, components: list[str], cause: str = "C01") -> Finding:
    return Finding(
        id=ids.finding_id(question, Tier.LIGHTNING.value, components, cause_id=cause),
        run_id=RUN,
        question_id=question,
        tier=Tier.LIGHTNING,
        cause_id=cause,
        failing_component_type=FailingComponentType.CONTROL_LOOP,
        failing_component_ids=components,
        consequence="something bad",
        adequacy=Adequacy.UNKNOWN,
        confidence=Confidence.SURE,
    )


def test_the_query_is_built_from_the_line_only() -> None:
    plant = Plant.model_validate_json(EXAMPLE.read_text(encoding="utf-8"))
    ref = load_reference_set()
    cause = next(c for c in ref.causes if c.id == "C01")
    section = Section(
        id="S-MX-1",
        plant_record_id="plant:test",
        kind=SectionKind.EQUIPMENT,
        section_type=SectionType.MIXER,
        name="S-MX-1",
        object_ids=["MX-1"],
        drawn_by="rule",
    )
    found = _finding("m:S-MX-1:more:temperature", ["TV-1"])
    query = query_for([(found, section)], plant, ref)
    words = set(tokens(query))
    assert set(tokens(cause.cause)) <= words
    assert {"more", "temperature", "mixer"} <= words
    for chemical in plant.chemicals:
        if chemical.id in ("SIH", "KOH"):
            assert set(tokens(chemical.name)) <= words
    # deterministic and free of IDs
    assert query == query_for([(found, section)], plant, ref)
    assert "f:" not in query and "S-MX-1" not in query
