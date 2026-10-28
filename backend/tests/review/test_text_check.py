"""Characters outside the expected scripts in stored model text are flagged, never altered
(Bhargavi, 2026-10-22: the final WG run's chain description ends with "互", Ultra's own
answer, and a Super finding's consequence ends with "水。")."""

from guideword.review.text_check import unexpected_characters, unexpected_flags, unfinished_flags


def test_a_cjk_character_is_named_by_its_code_point() -> None:
    assert unexpected_characters("…tube rupture (m:S-EA-425B:as_well_as:composition) that互") == [
        "U+4E92"
    ]
    assert unexpected_characters("release of hot水。") == ["U+6C34", "U+3002"]


def test_the_expected_scripts_pass() -> None:
    """Latin with accents, Greek, typographic punctuation (including the non-breaking hyphen
    Nemotron writes), units and maths symbols."""
    text = (
        "Café naïve façade — 85 °C, 2068 kPa ≥ 1.6× design; Δp ≈ 3 µm; non‑breaking hyphen; "
        "“quotes” ‘and’ apostrophes’; 10⁻⁴ per year → ½ … ±5 %\t\n"
    )
    assert unexpected_characters(text) == []


def test_each_code_point_is_named_once_in_order() -> None:
    assert unexpected_characters("a互b互c水") == ["U+4E92", "U+6C34"]


def test_the_flags_name_the_field_and_leave_the_text_as_it_is() -> None:
    text = "ends with that互"
    flags = unexpected_flags([("chain description", text), ("chain reason", "fine")])
    assert flags == ["unexpected character in model text: U+4E92 (chain description)"]
    assert text == "ends with that互"


# --- text with no closing punctuation (Bhargavi, 2026-10-28: F6 defect 7) ---------------------


def test_a_sentence_field_cut_off_is_flagged_and_left_as_it_is() -> None:
    text = "An upstream pump failure or feed-valve closure"
    flags = unfinished_flags([("chain description", text)])
    assert flags == ["text ends mid-sentence as stored (chain description)"]
    assert text == "An upstream pump failure or feed-valve closure"


def test_closing_punctuation_passes_even_inside_a_bracket_or_quote() -> None:
    fields = [
        ("chain description", "The shell is isolated."),
        ("chain reason", "Is that credible?"),
        ("chain severity reason", "It ruptures (see EA-425B.design_pressure_kpa)."),
        ("hypothesis reason", "The record says “closed.”"),
        ("hypothesis mechanism", "Steam flashes…  \n"),
        ("LOPA argument RV-1", "Credited."),
    ]
    assert unfinished_flags(fields) == []


def test_a_trailing_colon_or_open_bracket_is_mid_sentence() -> None:
    fields = [
        ("finding severity reason", "Premature relief valve opening on-site response: "),
        ("chain description", "overwhelming its relief valve (RV"),
    ]
    assert unfinished_flags(fields) == [
        "text ends mid-sentence as stored (finding severity reason)",
        "text ends mid-sentence as stored (chain description)",
    ]


def test_phrase_fields_and_empty_text_are_not_flagged() -> None:
    """A cause or consequence is written as a phrase ("valve left closed"), not a sentence."""
    fields = [
        ("finding cause", "Valve left closed"),
        ("finding consequence", "release of hot water into the building"),
        ("hypothesis cause", "Wrong tote charged"),
        ("chain reason", None),
        ("chain description", ""),
    ]
    assert unfinished_flags(fields) == []
