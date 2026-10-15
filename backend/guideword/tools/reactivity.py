"""`reactivity_lookup` (spec 2.3): what the EPA 1980 compatibility chart says about two
chemicals of the run's plant.

Every pair of the two chemicals' EPA groups is looked up. A pair the chart lists gives its
codes in words with the row's source; a pair it does not list is `not_listed`, never
"compatible" (the chart says a blank does not mean safe); a group marked do-not-mix (107,
water-reactive) gives `do_not_mix`. A chemical with no EPA groups is reported as such, with
its CAMEO groups for the specialist's judgment. The table owns the facts; this only reads it.
"""

from typing import Any

from guideword.reference import ReferenceSet
from guideword.reference.tables import ReactivityCode
from guideword.schema.plant import Chemical, Plant

TABLE = "reactive_pairs.csv"

# The chart's legend (EPA-600/2-80-076); PROJECT.md section 10 lists the same codes.
CODE_MEANINGS: dict[ReactivityCode, str] = {
    "H": "heat",
    "F": "fire",
    "G": "gas",
    "GT": "toxic gas",
    "GF": "flammable gas",
    "E": "explosion",
    "P": "violent polymerisation",
    "S": "solubilisation of toxic substance",
    "U": "unknown",
}


class ToolRefused(ValueError):
    """The arguments do not fit the plant; the reason goes back to the agent."""


def _chemical(plant: Plant, chemical_id: str) -> Chemical:
    for chemical in plant.chemicals:
        if chemical.id == chemical_id:
            return chemical
    raise ToolRefused(f"{chemical_id} is not a chemical in this plant")


def reactivity_lookup(
    plant: Plant, ref: ReferenceSet, chemical_a: str, chemical_b: str
) -> dict[str, Any]:
    if chemical_a == chemical_b:
        raise ToolRefused("reactivity_lookup needs two different chemicals")
    a = _chemical(plant, chemical_a)
    b = _chemical(plant, chemical_b)
    groups = {g.epa_group_id: g for g in ref.reactive_groups}
    cameo = {g.cameo_group_id: g.name for g in ref.cameo_groups}

    pairs = []
    for group_a in a.epa_groups:
        for group_b in b.epa_groups:
            found = ref.reactivity(group_a, group_b)
            if found.status == "listed" and found.row is not None:
                source = found.row.source
            elif found.status == "do_not_mix":
                marked = groups[group_a] if groups[group_a].do_not_mix else groups[group_b]
                source = marked.source
            else:
                source = f"no row in {TABLE}"
            pairs.append(
                {
                    "groups": [group_a, group_b],
                    "group_names": [groups[group_a].name, groups[group_b].name],
                    "status": found.status,
                    "codes": [{"code": c, "meaning": CODE_MEANINGS[c]} for c in found.codes],
                    "source": source,
                }
            )
    return {
        "chemicals": [
            {
                "id": c.id,
                "name": c.name,
                "epa_groups": list(c.epa_groups),
                "cameo_groups": [{"id": g, "name": cameo[g]} for g in c.cameo_groups if g in cameo],
            }
            for c in (a, b)
        ],
        "pairs": pairs,
        "no_groups": [c.id for c in (a, b) if not c.epa_groups],
        "table": TABLE,
    }
