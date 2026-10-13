"""Every numeric plant field names its unit (spec 0.5 unit-suffix rule, PROJECT.md §9)."""

import types
import typing
from typing import Any, Union

from pydantic import BaseModel

from guideword.schema import plant

# The list in PROJECT.md §9.
ALLOWED_SUFFIXES = (
    "_kpa",
    "_kpaa",
    "_c",
    "_m3",
    "_kg_h",
    "_kw",
    "_mm",
    "_m",
    "_pct",
    "_kj_kg",
    "_kg_m3",
    "_kj_kg_k",
    "_per_year",
    "_usd",
)

# Units fixed by `operating.parameter`, and reference-group IDs (integers that are not quantities).
EXEMPT = {
    ("Operating", "normal"),
    ("Operating", "alarm_low"),
    ("Operating", "alarm_high"),
    ("Operating", "trip_low"),
    ("Operating", "trip_high"),
    ("Operating", "design_min"),
    ("Operating", "design_max"),
    ("Chemical", "epa_groups"),
    ("Chemical", "cameo_groups"),
}


def _is_numeric(annotation: Any) -> bool:
    if annotation is bool:
        return False
    if annotation in (int, float):
        return True
    origin = typing.get_origin(annotation)
    if origin in (Union, types.UnionType, list, tuple, typing.Annotated):
        return any(_is_numeric(arg) for arg in typing.get_args(annotation))
    return False


def violations(models: list[type[BaseModel]]) -> list[str]:
    found = []
    for model in models:
        for name, field in model.model_fields.items():
            if not _is_numeric(field.annotation):
                continue
            if (model.__name__, name) in EXEMPT:
                continue
            if not name.endswith(ALLOWED_SUFFIXES):
                found.append(f"{model.__name__}.{name}")
    return found


def test_every_numeric_plant_field_has_a_unit_suffix() -> None:
    assert plant.PLANT_MODELS, "plant.PLANT_MODELS must list every plant model"
    assert violations(plant.PLANT_MODELS) == []


def test_check_fails_on_a_bare_numeric_field() -> None:
    class Bad(BaseModel):
        volume: float | None = None
        count_of_trays: int = 0
        ok_kpa: float = 0.0

    assert violations([Bad]) == ["Bad.volume", "Bad.count_of_trays"]


def test_every_model_in_the_module_is_listed() -> None:
    defined = {
        obj
        for name, obj in vars(plant).items()
        if isinstance(obj, type)
        and issubclass(obj, BaseModel)
        and obj.__module__ == plant.__name__
        and not name.startswith("_")  # private bases such as _Strict hold no fields
    }
    assert defined == set(plant.PLANT_MODELS)
