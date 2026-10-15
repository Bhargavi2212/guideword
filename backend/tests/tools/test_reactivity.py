"""The reactivity_lookup tool (spec 2.3): the EPA 1980 chart, never "compatible"."""

import json
from itertools import combinations
from pathlib import Path
from typing import Any

import pytest

from guideword.reference import ReferenceSet, load_reference_set
from guideword.schema.plant import Plant
from guideword.tools.reactivity import ToolRefused, reactivity_lookup

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"


@pytest.fixture(scope="module")
def ref() -> ReferenceSet:
    return load_reference_set()


def _plant(*extra: dict[str, Any]) -> Plant:
    data: dict[str, Any] = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["chemicals"] += list(extra)
    return Plant.model_validate(data)


def _pair(result: dict[str, Any], a: int, b: int) -> dict[str, Any]:
    pair: dict[str, Any] = next(p for p in result["pairs"] if sorted(p["groups"]) == sorted([a, b]))
    return pair


def test_sih_koh_is_listed_gf_gt_from_105_x_106_with_source(ref: ReferenceSet) -> None:
    result = reactivity_lookup(_plant(), ref, "SIH", "KOH")
    pair = _pair(result, 105, 106)
    assert pair["status"] == "listed"
    assert {c["code"] for c in pair["codes"]} == {"GF", "GT"}
    meanings = {c["code"]: c["meaning"] for c in pair["codes"]}
    assert meanings == {"GF": "flammable gas", "GT": "toxic gas"}
    assert "EPA-600/2-80-076" in pair["source"]
    # every combination of SIH's groups [105] with KOH's [10, 106] is reported
    assert sorted(sorted(p["groups"]) for p in result["pairs"]) == [[10, 105], [105, 106]]


def test_the_result_names_both_chemicals_and_the_table(ref: ReferenceSet) -> None:
    result = reactivity_lookup(_plant(), ref, "KOH", "SIH")
    assert [c["id"] for c in result["chemicals"]] == ["KOH", "SIH"]
    assert result["table"] == "reactive_pairs.csv"
    assert result["no_groups"] == []


def _unlisted_pair(ref: ReferenceSet) -> tuple[int, int]:
    listed = {frozenset((p.group_a, p.group_b)) for p in ref.reactive_pairs}
    groups = sorted(g.epa_group_id for g in ref.reactive_groups if not g.do_not_mix)
    return next((a, b) for a, b in combinations(groups, 2) if frozenset((a, b)) not in listed)


def test_pair_without_a_row_is_not_listed(ref: ReferenceSet) -> None:
    a, b = _unlisted_pair(ref)
    plant = _plant(
        {"id": "CHEM-A", "name": "a", "epa_groups": [a]},
        {"id": "CHEM-B", "name": "b", "epa_groups": [b]},
    )
    result = reactivity_lookup(plant, ref, "CHEM-A", "CHEM-B")
    pair = _pair(result, a, b)
    assert pair["status"] == "not_listed"
    assert pair["codes"] == []
    assert "compatible" not in json.dumps(result).lower().replace("incompatib", "")


def test_group_107_is_do_not_mix(ref: ReferenceSet) -> None:
    plant = _plant({"id": "NA", "name": "sodium", "epa_groups": [107]})
    result = reactivity_lookup(plant, ref, "NA", "KOH")
    assert {p["status"] for p in result["pairs"]} == {"do_not_mix"}
    assert all(p["source"] for p in result["pairs"])


def test_chemical_without_groups_is_no_groups_with_cameo(ref: ReferenceSet) -> None:
    cameo = ref.cameo_groups[0]
    plant = _plant({"id": "MYST", "name": "unknown oil", "cameo_groups": [cameo.cameo_group_id]})
    result = reactivity_lookup(plant, ref, "MYST", "SIH")
    assert result["no_groups"] == ["MYST"]
    assert result["pairs"] == []
    myst = next(c for c in result["chemicals"] if c["id"] == "MYST")
    assert myst["cameo_groups"] == [{"id": cameo.cameo_group_id, "name": cameo.name}]


@pytest.mark.parametrize(
    ("a", "b", "reason"),
    [
        ("SIH", "NOPE", "NOPE is not a chemical in this plant"),
        ("MX-1", "SIH", "MX-1 is not a chemical in this plant"),
        ("SIH", "SIH", "two different chemicals"),
    ],
)
def test_unknown_chemical_is_refused_with_a_reason(
    ref: ReferenceSet, a: str, b: str, reason: str
) -> None:
    with pytest.raises(ToolRefused, match=reason):
        reactivity_lookup(_plant(), ref, a, b)
