"""Case lint (Phase 9 spec 9.0): a package written "before the accident" must not carry the
date, the site, the company, the outcome or the investigators' words. Deterministic word lists
and patterns; no model."""

from pathlib import Path

import pytest

from guideword.bench.caselint import Flag, LintTerm, lint_text, load_lint_terms
from guideword.reference import ReferenceTableError

SOURCE = "docs/case-template.md section 2 (no hints; neutral identities)"


def terms() -> tuple[LintTerm, ...]:
    return (
        LintTerm(term="explosion", kind="outcome", source=SOURCE),
        LintTerm(term="should have", kind="hint", source=SOURCE),
        LintTerm(term="CSB", kind="investigator", source=SOURCE),
    )


def kinds(flags: list[Flag]) -> list[tuple[int, str]]:
    return [(f.line, f.kind) for f in flags]


def test_a_year_is_flagged_with_its_line() -> None:
    flags = lint_text("# Plant K\n\nThe unit was built in 2011 and debottlenecked.\n", terms())
    assert kinds(flags) == [(3, "year")]
    assert flags[0].text == "2011"


def test_a_number_that_is_not_a_year_is_not_flagged() -> None:
    text = "design pressure 1950 kPa; flow 2000 kg/h; 100 m3; tag 2011-A; the 2010 pump"
    assert lint_text(text, terms()) == []


def test_a_year_in_a_date_or_at_a_sentence_end_is_flagged() -> None:
    text = "Commissioned in May 2008.\nThe turnaround of 2019.\nRevamped 2015, then idle\n"
    text += "Inspected on 12 March 2021 and again later\n"
    flags = lint_text(text, terms())
    assert [(f.line, f.text) for f in flags] == [(1, "2008"), (2, "2019"), (3, "2015"), (4, "2021")]


def test_outcome_hint_and_investigator_terms_match_whole_words_in_any_case() -> None:
    text = "An EXPLOSION risk.\nThe operators should have known.\nThe csb report.\nexplosions\n"
    flags = lint_text(text, terms())
    assert kinds(flags) == [(1, "outcome"), (2, "hint"), (3, "investigator")]
    assert [f.text for f in flags] == ["EXPLOSION", "should have", "csb"]


def test_a_hyphenated_compound_is_not_the_bare_term() -> None:
    assert lint_text("explosion-proof motors throughout", terms()) == []


def test_a_company_like_name_is_flagged() -> None:
    flags = lint_text("The site is operated by Acme Chemicals Inc under a permit.", terms())
    assert kinds(flags) == [(1, "company")]
    assert flags[0].text == "Acme Chemicals Inc"


def test_a_town_and_region_pair_is_flagged() -> None:
    flags = lint_text("The plant lies in Geismar, Louisiana near the river.", terms())
    assert kinds(flags) == [(1, "place")]


def test_flags_on_one_line_come_in_position_order() -> None:
    flags = lint_text("rebuilt after an explosion in 2011", terms())
    assert kinds(flags) == [(1, "outcome"), (1, "year")]


def test_a_clean_package_in_the_template_shape_passes() -> None:
    text = (
        "# Plant K: batch polymerisation unit\n\n## Data package\n\n**Major equipment**\n"
        "- R-1 jacketed reactor, 10 m3, design pressure 350 kPa gauge, MAWT 150 C\n"
        "- E-1 overhead condenser, cooling water on the shell side\n"
        "**Lines and connections**\n- 50 mm line from R-1 to E-1, normally open\n"
        "**Procedures**\n1. Charge solvent to R-1 through the manway\n"
        "**Surroundings**\n- a control room 30 m from R-1, occupied on day shift\n"
        "## Task\nPerform a full HAZOP of this unit.\n"
    )
    assert lint_text(text, terms()) == []


def test_terms_load_from_a_csv_with_a_source_on_every_row(tmp_path: Path) -> None:
    good = tmp_path / "good"
    good.mkdir()
    (good / "case_lint_terms.csv").write_text(
        "term,kind,source\nexplosion,outcome,a source\n", encoding="utf-8", newline="\n"
    )
    loaded = load_lint_terms(good)
    assert loaded == (LintTerm(term="explosion", kind="outcome", source="a source"),)
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "case_lint_terms.csv").write_text(
        "term,kind,source\nexplosion,outcome,\n", encoding="utf-8", newline="\n"
    )
    with pytest.raises(ReferenceTableError):
        load_lint_terms(bad)


def test_an_unknown_kind_is_refused(tmp_path: Path) -> None:
    (tmp_path / "case_lint_terms.csv").write_text(
        "term,kind,source\nexplosion,verdict,a source\n", encoding="utf-8", newline="\n"
    )
    with pytest.raises(ReferenceTableError):
        load_lint_terms(tmp_path)


def test_the_shipped_terms_table_loads_and_names_the_three_kinds() -> None:
    shipped = load_lint_terms()
    assert {t.kind for t in shipped} == {"outcome", "hint", "investigator"}
    assert all(t.source for t in shipped)
