"""One typed row model per reference table (PROJECT.md §10). Headers are frozen at G1.

Cells arrive as CSV strings: an empty cell is "no value", multi-value cells use `;`, and
flag columns accept only "0" or "1".
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator

from guideword.schema.enums import (
    FailingComponentType,
    Guideword,
    HazopParameter,
    LikelihoodClass,
    ReliefKind,
    RiskRating,
    SectionType,
    SeverityClass,
)

FrequencyUnit = Literal["per_year", "per_opportunity", "per_metre_year", "per_lift"]
ReactivityCode = Literal["H", "F", "G", "GT", "GF", "E", "P", "S", "U"]
LayerCategory = Literal["active", "passive", "human"]

CAUSE_TARGETS = frozenset({s.value for s in SectionType} | {"planned_work"})


def _flag(value: object) -> bool:
    if value not in ("0", "1", 0, 1):
        raise ValueError(f"flag must be 0 or 1, got {value!r}")
    return value in ("1", 1)


def _split(value: object) -> object:
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(";") if part.strip())
    return value


Flag = Annotated[bool, BeforeValidator(_flag)]
Probability = Annotated[float, Field(gt=0, le=1)]
Source = Annotated[str, Field(min_length=1)]


class _Row(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="before")
    @classmethod
    def _empty_cells_are_missing(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {
                k: (None if isinstance(v, str) and not v.strip() else v) for k, v in data.items()
            }
        return data


class ApplicabilityRow(_Row):
    section_type: SectionType
    guideword: Guideword
    parameter: HazopParameter
    source: Source


class CauseRow(_Row):
    id: str
    cause: str
    applies_to: Annotated[tuple[str, ...], BeforeValidator(_split), Field(min_length=1)]
    failing_component_type: FailingComponentType
    initiating_event_id: str
    source: Source

    @field_validator("applies_to")
    @classmethod
    def _known_targets(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        unknown = set(value) - CAUSE_TARGETS
        if unknown:
            raise ValueError(f"applies_to has unknown section types: {sorted(unknown)}")
        return value


class InitiatingEventRow(_Row):
    id: str
    event: str
    frequency: Annotated[float, Field(gt=0)]
    unit: FrequencyUnit
    source: Source

    @property
    def frequency_per_year(self) -> float | None:
        """The yearly frequency, or None when the unit needs a plant fact to convert (Phase 3)."""
        return self.frequency if self.unit == "per_year" else None


class ProtectionLayerRow(_Row):
    id: str
    layer: str
    category: LayerCategory
    pfd: Probability
    pfd_if_isolatable: Probability | None = None
    requires_independent_sensor: Flag
    requires_independent_logic: Flag
    requires_independent_final_element: Flag
    no_credit_if_isolated: Flag
    scenarios: Annotated[tuple[str, ...], BeforeValidator(_split), Field(min_length=1)]
    conditions_text: str
    relief_kind: ReliefKind | None = None
    source: Source


class ModifierRow(_Row):
    id: str
    kind: str
    release_phase: str
    release_rate_kg_s_band: str
    area_occupancy: str
    event_type: str
    operating_pattern: str
    value: Probability
    source: Source


class SeverityClassRow(_Row):
    severity_class: SeverityClass
    name: str
    definition: str
    source: Source


class TolerableFrequencyRow(_Row):
    severity_class: SeverityClass
    tolerable_per_year: Annotated[float, Field(gt=0)]
    source: Source


class LikelihoodClassRow(_Row):
    likelihood_class: LikelihoodClass
    name: str
    min_per_year: Annotated[float, Field(ge=0)]
    max_per_year: Annotated[float, Field(gt=0)] | None = None
    source: Source


class RiskMatrixRow(_Row):
    severity_class: SeverityClass
    likelihood_class: LikelihoodClass
    rating: RiskRating
    source: Source


class CameoGroupRow(_Row):
    cameo_group_id: int
    name: str
    source: Source


class ReactiveGroupRow(_Row):
    epa_group_id: int
    name: str
    do_not_mix: Flag
    source: Source


class ReactivePairRow(_Row):
    group_a: int
    group_b: int
    codes: Annotated[tuple[ReactivityCode, ...], BeforeValidator(_split), Field(min_length=1)]
    source: Source
