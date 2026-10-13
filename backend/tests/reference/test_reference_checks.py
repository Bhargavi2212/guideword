"""The loader refuses broken tables (spec 0.6). Each test breaks one thing in a temp copy."""

import re
from collections.abc import Callable
from pathlib import Path

import pytest

from guideword.reference import ReferenceTableError, load_reference_set

Edit = Callable[[str, Callable[[str], str]], None]


def _sub(pattern: str, replacement: str, count: int = 1) -> Callable[[str], str]:
    def change(text: str) -> str:
        new, n = re.subn(pattern, replacement, text, count=count, flags=re.M)
        assert n, f"test pattern did not match: {pattern}"
        return new

    return change


def _refused(directory: Path, table: str) -> None:
    with pytest.raises(ReferenceTableError, match=re.escape(table)):
        load_reference_set(directory)


def test_copy_loads_unchanged(reference_copy: Path) -> None:
    load_reference_set(reference_copy)


def test_wrong_header(reference_copy: Path, edit_table: Edit) -> None:
    edit_table("causes.csv", _sub(r"^id,cause,", "id,name,"))
    _refused(reference_copy, "causes.csv")


def test_empty_source(reference_copy: Path, edit_table: Edit) -> None:
    edit_table("severity_classes.csv", _sub(r'^(S1,Minor,[^\n]*?),"[^"\n]*"$', r'\1,""'))
    _refused(reference_copy, "severity_classes.csv")


def test_carriage_return(reference_copy: Path, edit_table: Edit) -> None:
    edit_table("tolerable_frequencies.csv", lambda t: t.replace("\n", "\r\n", 1))
    _refused(reference_copy, "tolerable_frequencies.csv")


def test_missing_table(reference_copy: Path) -> None:
    (reference_copy / "risk_matrix.csv").unlink()
    _refused(reference_copy, "risk_matrix.csv")


# --- applicability ------------------------------------------------------------------------


def test_duplicate_applicability_row(reference_copy: Path, edit_table: Edit) -> None:
    edit_table("applicability.csv", lambda t: t + t.splitlines()[1] + "\n")
    _refused(reference_copy, "applicability.csv")


def test_applicability_unknown_guideword(reference_copy: Path, edit_table: Edit) -> None:
    edit_table("applicability.csv", _sub(r"^pipe,no,flow,", "pipe,never,flow,"))
    _refused(reference_copy, "applicability.csv")


def test_section_type_without_rows(reference_copy: Path, edit_table: Edit) -> None:
    edit_table("applicability.csv", _sub(r"^pump,[^\n]*\n", "", count=0))
    _refused(reference_copy, "applicability.csv")


# --- causes and events ----------------------------------------------------------------------


def test_duplicate_cause_id(reference_copy: Path, edit_table: Edit) -> None:
    edit_table("causes.csv", _sub(r"^C02,", "C01,"))
    _refused(reference_copy, "causes.csv")


def test_cause_with_missing_event(reference_copy: Path, edit_table: Edit) -> None:
    edit_table("causes.csv", _sub(r",IE-BPCS,", ",IE-NOPE,"))
    _refused(reference_copy, "causes.csv")


def test_cause_applies_to_unknown_type(reference_copy: Path, edit_table: Edit) -> None:
    edit_table("causes.csv", _sub(r"^(C06,Pump seal fails,)pump,", r"\1boiler,"))
    _refused(reference_copy, "causes.csv")


def test_cause_unknown_failing_type(reference_copy: Path, edit_table: Edit) -> None:
    edit_table("causes.csv", _sub(r"^(C06,Pump seal fails,pump,)pump,", r"\1gasket,"))
    _refused(reference_copy, "causes.csv")


def test_zero_frequency(reference_copy: Path, edit_table: Edit) -> None:
    edit_table(
        "initiating_events.csv", _sub(r"^(IE-BPCS,BPCS control loop failure,)0\.1,", r"\g<1>0,")
    )
    _refused(reference_copy, "initiating_events.csv")


def test_unknown_frequency_unit(reference_copy: Path, edit_table: Edit) -> None:
    edit_table("initiating_events.csv", _sub(r",0\.1,per_year,", ",0.1,per_month,"))
    _refused(reference_copy, "initiating_events.csv")


# --- protection layers and modifiers ------------------------------------------------------


def test_pfd_above_one(reference_copy: Path, edit_table: Edit) -> None:
    edit_table("protection_layers.csv", _sub(r"^(IPL-PRV,[^,]*,active,)0\.01,", r"\g<1>1.5,"))
    _refused(reference_copy, "protection_layers.csv")


def test_flag_not_zero_or_one(reference_copy: Path, edit_table: Edit) -> None:
    edit_table("protection_layers.csv", _sub(r"^(IPL-PRV,[^,]*,active,0\.01,0\.1,)0,", r"\g<1>2,"))
    _refused(reference_copy, "protection_layers.csv")


def test_flag_spelled_as_word(reference_copy: Path, edit_table: Edit) -> None:
    edit_table("protection_layers.csv", _sub(r"^(IPL-PRV,[^,]*,active,0\.01,0\.1,)0,", r"\1true,"))
    _refused(reference_copy, "protection_layers.csv")


def test_duplicate_relief_kind(reference_copy: Path, edit_table: Edit) -> None:
    edit_table("protection_layers.csv", _sub(r",rupture_disk,", ",prv,"))
    _refused(reference_copy, "protection_layers.csv")


def test_missing_relief_kind(reference_copy: Path, edit_table: Edit) -> None:
    edit_table("protection_layers.csv", _sub(r",vent,", ",,"))
    _refused(reference_copy, "protection_layers.csv")


def test_modifier_value_zero(reference_copy: Path, edit_table: Edit) -> None:
    edit_table("modifiers.csv", _sub(r"^(MOD-IGN-GAS-S,[^\n]*?,)0\.01,", r"\g<1>0,"))
    _refused(reference_copy, "modifiers.csv")


# --- severity, likelihood, risk -----------------------------------------------------------


def test_severity_class_twice(reference_copy: Path, edit_table: Edit) -> None:
    edit_table("tolerable_frequencies.csv", _sub(r"^S2,", "S1,"))
    _refused(reference_copy, "tolerable_frequencies.csv")


def test_likelihood_gap(reference_copy: Path, edit_table: Edit) -> None:
    edit_table("likelihood_classes.csv", _sub(r"^(L3,Possible,)0\.001,", r"\g<1>0.002,"))
    _refused(reference_copy, "likelihood_classes.csv")


def test_likelihood_lowest_band_not_from_zero(reference_copy: Path, edit_table: Edit) -> None:
    edit_table("likelihood_classes.csv", _sub(r"^(L1,Remote,)0,", r"\g<1>0.00001,"))
    _refused(reference_copy, "likelihood_classes.csv")


def test_likelihood_top_band_closed(reference_copy: Path, edit_table: Edit) -> None:
    edit_table("likelihood_classes.csv", _sub(r"^(L5,Frequent,0\.1,),", r"\g<1>1,"))
    _refused(reference_copy, "likelihood_classes.csv")


def test_risk_matrix_missing_pair(reference_copy: Path, edit_table: Edit) -> None:
    edit_table("risk_matrix.csv", _sub(r"^S3,L4,[^\n]*\n", ""))
    _refused(reference_copy, "risk_matrix.csv")


def test_risk_matrix_unknown_rating(reference_copy: Path, edit_table: Edit) -> None:
    edit_table("risk_matrix.csv", _sub(r"^(S1,L1,)low,", r"\1tiny,"))
    _refused(reference_copy, "risk_matrix.csv")


# --- reactive groups and pairs ----------------------------------------------------------------


def test_do_not_mix_not_zero_or_one(reference_copy: Path, edit_table: Edit) -> None:
    edit_table("reactive_groups.csv", _sub(r"^(107,Water Reactive Substances,)1,", r"\g<1>yes,"))
    _refused(reference_copy, "reactive_groups.csv")


def test_pair_with_unknown_group(reference_copy: Path, edit_table: Edit) -> None:
    edit_table("reactive_pairs.csv", _sub(r"^2,3,", "2,999,"))
    _refused(reference_copy, "reactive_pairs.csv")


def test_pair_with_unknown_code(reference_copy: Path, edit_table: Edit) -> None:
    edit_table("reactive_pairs.csv", _sub(r"^2,3,H;G,", "2,3,H;X,"))
    _refused(reference_copy, "reactive_pairs.csv")


def test_pair_listed_twice_in_reverse(reference_copy: Path, edit_table: Edit) -> None:
    edit_table("reactive_pairs.csv", lambda t: t + '3,2,H,"src"\n')
    _refused(reference_copy, "reactive_pairs.csv")


def test_pair_out_of_chart_order(reference_copy: Path, edit_table: Edit) -> None:
    edit_table("reactive_pairs.csv", _sub(r"^2,3,", "3,2,"))
    _refused(reference_copy, "reactive_pairs.csv")


def test_pair_with_group_107(reference_copy: Path, edit_table: Edit) -> None:
    edit_table("reactive_pairs.csv", lambda t: t + '106,107,H,"src"\n')
    _refused(reference_copy, "reactive_pairs.csv")


def test_duplicate_cameo_group(reference_copy: Path, edit_table: Edit) -> None:
    edit_table("cameo_groups.csv", _sub(r"^2,", "1,"))
    _refused(reference_copy, "cameo_groups.csv")


# --- versions ---------------------------------------------------------------------------------


def test_version_hash_changes_when_a_file_changes(reference_copy: Path, edit_table: Edit) -> None:
    before = load_reference_set(reference_copy).versions
    edit_table("severity_classes.csv", _sub("First aid", "First-aid"))
    after = load_reference_set(reference_copy).versions
    assert after["severity_classes.csv"] != before["severity_classes.csv"]
    unchanged = set(before) - {"severity_classes.csv"}
    assert all(after[name] == before[name] for name in unchanged)
