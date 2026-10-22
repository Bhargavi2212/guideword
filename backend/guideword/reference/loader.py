"""Loads and checks the reference tables; stamps each with its version hash (spec 0.6).

Values come from the sources in reference/sources.md and are never changed by code. A pair
missing from the EPA chart is "not listed", never "compatible": the chart says blanks do
not mean a mixture is safe.
"""

import csv
import hashlib
import io
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

from guideword.reference.tables import (
    ApplicabilityRow,
    CameoGroupRow,
    CauseRow,
    InitiatingEventRow,
    LikelihoodClassRow,
    ModifierRow,
    ProtectionLayerRow,
    ReactiveGroupRow,
    ReactivePairRow,
    ReactivityCode,
    RiskMatrixRow,
    SeverityClassRow,
    TolerableFrequencyRow,
)
from guideword.schema.enums import (
    Guideword,
    LikelihoodClass,
    ReliefKind,
    SectionType,
    SeverityClass,
)

FROZEN_HEADERS: dict[str, tuple[str, ...]] = {
    "applicability.csv": ("section_type", "guideword", "parameter", "source"),
    "causes.csv": (
        "id",
        "cause",
        "applies_to",
        "failing_component_type",
        "initiating_event_id",
        "source",
    ),
    "initiating_events.csv": ("id", "event", "frequency", "unit", "source"),
    "protection_layers.csv": (
        "id",
        "layer",
        "category",
        "pfd",
        "pfd_if_isolatable",
        "requires_independent_sensor",
        "requires_independent_logic",
        "requires_independent_final_element",
        "no_credit_if_isolated",
        "scenarios",
        "conditions_text",
        "relief_kind",
        "source",
    ),
    "modifiers.csv": (
        "id",
        "kind",
        "release_phase",
        "release_rate_kg_s_band",
        "area_occupancy",
        "event_type",
        "operating_pattern",
        "value",
        "source",
    ),
    "severity_classes.csv": ("severity_class", "name", "definition", "source"),
    "tolerable_frequencies.csv": ("severity_class", "tolerable_per_year", "source"),
    "likelihood_classes.csv": (
        "likelihood_class",
        "name",
        "min_per_year",
        "max_per_year",
        "source",
    ),
    "risk_matrix.csv": ("severity_class", "likelihood_class", "rating", "source"),
    "cameo_groups.csv": ("cameo_group_id", "name", "source"),
    "reactive_groups.csv": ("epa_group_id", "name", "do_not_mix", "source"),
    "reactive_pairs.csv": ("group_a", "group_b", "codes", "source"),
}

DEFAULT_REFERENCE_DIR = Path(__file__).resolve().parents[3] / "reference"


class ReferenceTableError(ValueError):
    """A reference table is missing, malformed or fails a consistency check."""

    def __init__(self, table: str, message: str) -> None:
        super().__init__(f"{table}: {message}")
        self.table = table


@dataclass(frozen=True)
class Reactivity:
    """`listed` (codes and the chart row), `not_listed` (never "compatible"), or `do_not_mix`."""

    status: Literal["listed", "not_listed", "do_not_mix"]
    codes: tuple[ReactivityCode, ...] = ()
    row: ReactivePairRow | None = None


@dataclass(frozen=True)
class ReferenceSet:
    applicability: tuple[ApplicabilityRow, ...]
    causes: tuple[CauseRow, ...]
    initiating_events: tuple[InitiatingEventRow, ...]
    protection_layers: tuple[ProtectionLayerRow, ...]
    modifiers: tuple[ModifierRow, ...]
    severity_classes: tuple[SeverityClassRow, ...]
    tolerable_frequencies: tuple[TolerableFrequencyRow, ...]
    likelihood_classes: tuple[LikelihoodClassRow, ...]
    risk_matrix: tuple[RiskMatrixRow, ...]
    cameo_groups: tuple[CameoGroupRow, ...]
    reactive_groups: tuple[ReactiveGroupRow, ...]
    reactive_pairs: tuple[ReactivePairRow, ...]
    # file name -> SHA-256 of the file bytes; a run records these
    versions: Mapping[str, str]

    @property
    def procedure_guidewords(self) -> tuple[Guideword, ...]:
        """The guideword list for `proc:` questions, in file order."""
        return tuple(
            row.guideword for row in self.applicability if row.section_type == SectionType.PROCEDURE
        )

    def initiating_event(self, event_id: str) -> InitiatingEventRow:
        for row in self.initiating_events:
            if row.id == event_id:
                return row
        raise KeyError(event_id)

    def layer_for_relief_kind(self, kind: ReliefKind) -> ProtectionLayerRow:
        for row in self.protection_layers:
            if row.relief_kind == kind:
                return row
        raise KeyError(kind)

    def reactivity(self, group_a: int, group_b: int) -> Reactivity:
        """EPA chart lookup for two reactive groups, in either order."""
        groups = {g.epa_group_id: g for g in self.reactive_groups}
        for group in (group_a, group_b):
            if group not in groups:
                raise KeyError(group)
        if groups[group_a].do_not_mix or groups[group_b].do_not_mix:
            return Reactivity("do_not_mix")
        wanted = frozenset((group_a, group_b))
        for row in self.reactive_pairs:
            if frozenset((row.group_a, row.group_b)) == wanted:
                return Reactivity("listed", row.codes, row)
        return Reactivity("not_listed")


# --- reading ------------------------------------------------------------------------------


def _read[Row: BaseModel](
    directory: Path, name: str, model: type[Row], header: tuple[str, ...] | None = None
) -> tuple[tuple[Row, ...], str]:
    """One table: LF, UTF-8, its frozen header (FROZEN_HEADERS, or `header` for a table
    loaded outside the ReferenceSet), each row validated; with its SHA-256."""
    path = directory / name
    if not path.is_file():
        raise ReferenceTableError(name, "file is missing")
    data = path.read_bytes()
    if b"\r" in data:
        raise ReferenceTableError(name, "contains a carriage return; files must use LF")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ReferenceTableError(name, f"not UTF-8: {error}") from error
    reader = csv.reader(io.StringIO(text, newline=""))
    frozen = header if header is not None else FROZEN_HEADERS[name]
    header = tuple(next(reader, ()))
    if header != frozen:
        raise ReferenceTableError(name, f"header {header} is not the frozen header")
    rows = []
    for line, values in enumerate(reader, start=2):
        if len(values) != len(header):
            raise ReferenceTableError(name, f"row {line} has {len(values)} cells")
        try:
            rows.append(model.model_validate(dict(zip(header, values, strict=True))))
        except ValidationError as error:
            raise ReferenceTableError(name, f"row {line}: {error}") from error
    if not rows:
        raise ReferenceTableError(name, "has no rows")
    return tuple(rows), hashlib.sha256(data).hexdigest()


def _unique(name: str, keys: list[object]) -> None:
    repeated = [k for k, n in Counter(keys).items() if n > 1]
    if repeated:
        raise ReferenceTableError(name, f"repeated keys: {repeated}")


def _once_each(name: str, keys: list[object], expected: set[object]) -> None:
    _unique(name, keys)
    if set(keys) != expected:
        raise ReferenceTableError(name, f"must list each of {sorted(map(str, expected))} once")


# --- checks across rows and tables -----------------------------------------------------------


def _check(ref: ReferenceSet) -> None:
    applicability = [(r.section_type, r.guideword, r.parameter) for r in ref.applicability]
    _unique("applicability.csv", list(applicability))
    missing = set(SectionType) - {r.section_type for r in ref.applicability}
    if missing:
        raise ReferenceTableError("applicability.csv", f"no rows for {sorted(missing)}")

    _unique("initiating_events.csv", [r.id for r in ref.initiating_events])
    events = {r.id for r in ref.initiating_events}
    _unique("causes.csv", [r.id for r in ref.causes])
    for cause in ref.causes:
        if cause.initiating_event_id not in events:
            raise ReferenceTableError(
                "causes.csv", f"{cause.id} names missing event {cause.initiating_event_id}"
            )

    _unique("protection_layers.csv", [r.id for r in ref.protection_layers])
    kinds = [r.relief_kind for r in ref.protection_layers if r.relief_kind is not None]
    _once_each("protection_layers.csv", list(kinds), set(ReliefKind))
    _unique("modifiers.csv", [r.id for r in ref.modifiers])

    _once_each(
        "severity_classes.csv", [r.severity_class for r in ref.severity_classes], set(SeverityClass)
    )
    _once_each(
        "tolerable_frequencies.csv",
        [r.severity_class for r in ref.tolerable_frequencies],
        set(SeverityClass),
    )
    _check_likelihood(ref.likelihood_classes)
    _once_each(
        "risk_matrix.csv",
        [(r.severity_class, r.likelihood_class) for r in ref.risk_matrix],
        {(s, lk) for s in SeverityClass for lk in LikelihoodClass},
    )

    _unique("cameo_groups.csv", [r.cameo_group_id for r in ref.cameo_groups])
    _unique("reactive_groups.csv", [r.epa_group_id for r in ref.reactive_groups])
    _check_pairs(ref.reactive_groups, ref.reactive_pairs)


def _check_likelihood(bands: tuple[LikelihoodClassRow, ...]) -> None:
    name = "likelihood_classes.csv"
    _once_each(name, [b.likelihood_class for b in bands], set(LikelihoodClass))
    ordered = sorted(bands, key=lambda b: b.min_per_year)
    if ordered[0].min_per_year != 0:
        raise ReferenceTableError(name, "the lowest band must start at 0")
    for lower, upper in zip(ordered, ordered[1:], strict=False):
        if lower.max_per_year != upper.min_per_year:
            raise ReferenceTableError(
                name, f"{lower.likelihood_class} and {upper.likelihood_class} do not meet"
            )
    if ordered[-1].max_per_year is not None:
        raise ReferenceTableError(name, "the top band's max_per_year must be empty (no limit)")
    for band in ordered[:-1]:
        if band.max_per_year is None or band.max_per_year <= band.min_per_year:
            raise ReferenceTableError(name, f"{band.likelihood_class} is empty or reversed")


def _check_pairs(groups: tuple[ReactiveGroupRow, ...], pairs: tuple[ReactivePairRow, ...]) -> None:
    name = "reactive_pairs.csv"
    order = {g.epa_group_id: i for i, g in enumerate(groups)}
    do_not_mix = {g.epa_group_id for g in groups if g.do_not_mix}
    seen: set[frozenset[int]] = set()
    for pair in pairs:
        for group in (pair.group_a, pair.group_b):
            if group not in order:
                raise ReferenceTableError(name, f"unknown group {group}")
            if group in do_not_mix:
                raise ReferenceTableError(name, f"group {group} is do-not-mix and has no pairs")
        if order[pair.group_a] >= order[pair.group_b]:
            raise ReferenceTableError(
                name, f"{pair.group_a},{pair.group_b}: group_a must come first in chart order"
            )
        key = frozenset((pair.group_a, pair.group_b))
        if key in seen:
            raise ReferenceTableError(name, f"pair {pair.group_a},{pair.group_b} listed twice")
        seen.add(key)


def load_reference_set(directory: Path | None = None) -> ReferenceSet:
    """Load every table from `directory` (default: the repo's reference/) and check it."""
    root = directory if directory is not None else DEFAULT_REFERENCE_DIR
    versions: dict[str, str] = {}

    def read[Row: BaseModel](name: str, model: type[Row]) -> tuple[Row, ...]:
        rows, version = _read(root, name, model)
        versions[name] = version
        return rows

    ref = ReferenceSet(
        applicability=read("applicability.csv", ApplicabilityRow),
        causes=read("causes.csv", CauseRow),
        initiating_events=read("initiating_events.csv", InitiatingEventRow),
        protection_layers=read("protection_layers.csv", ProtectionLayerRow),
        modifiers=read("modifiers.csv", ModifierRow),
        severity_classes=read("severity_classes.csv", SeverityClassRow),
        tolerable_frequencies=read("tolerable_frequencies.csv", TolerableFrequencyRow),
        likelihood_classes=read("likelihood_classes.csv", LikelihoodClassRow),
        risk_matrix=read("risk_matrix.csv", RiskMatrixRow),
        cameo_groups=read("cameo_groups.csv", CameoGroupRow),
        reactive_groups=read("reactive_groups.csv", ReactiveGroupRow),
        reactive_pairs=read("reactive_pairs.csv", ReactivePairRow),
        versions=versions,
    )
    _check(ref)
    return ref
