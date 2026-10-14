"""Plant loading, plant facts and the plant store (spec 1.1).

A plant is stored only when it validates with no errors. Its record ID is built from the
file exactly as uploaded, so the same file is the same record and a changed file a new one.
Facts are never filled in: a fact with no source is "not stated" and flagged.
"""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from guideword.reference import ReferenceSet
from guideword.runs.db import PlantFactRow, PlantRow, SectionRow
from guideword.schema import ids
from guideword.schema.enums import OPERATING_LIMITS, PlantStatus
from guideword.schema.plant import Chemical, Plant, Procedure
from guideword.schema.records import PlantFact, PlantRecord, Section
from guideword.schema.validate import Issue, ValidationReport, validate_plant

NOT_STATED = "not stated"
SOURCE_NOT_STATED = "source_not_stated"

# Fields of a plant object that are not facts about it (P10, Q3).
_NOT_FACTS = {"id", "notes"}
_NOT_FACTS_BY_TYPE: dict[type[BaseModel], set[str]] = {
    # the steps are plant objects with their own facts
    Procedure: {"steps"},
    # the chemical's source is where its facts come from, not a fact
    Chemical: {"source"},
}


def load_plant(
    data: Mapping[str, Any], ref: ReferenceSet
) -> tuple[PlantRecord | None, ValidationReport]:
    """Validate a plant file; with no errors, the record to store (status `uploaded`)."""
    report = validate_plant(data, ref)
    if not report.ok or report.plant is None:
        return None, report
    plant = report.plant
    record = PlantRecord(
        id=ids.plant_record_id(plant.plant_id, data),
        plant_id=plant.plant_id,
        plant_file=plant,
        status=PlantStatus.UPLOADED,
    )
    return record, report


def _plant_objects(plant: Plant) -> Iterator[BaseModel]:
    """Every plant object with an ID, procedure steps included."""
    for name in type(plant).model_fields:
        value = getattr(plant, name)
        if not isinstance(value, list):
            continue
        for item in value:
            if isinstance(item, BaseModel) and "id" in type(item).model_fields:
                yield item
                if isinstance(item, Procedure):
                    yield from item.steps


def plant_facts(plant: Plant, plant_record_id: str) -> list[PlantFact]:
    """One fact per stated top-level field of every plant object, plus one per operating limit.

    A value object is one fact at its parent's field. Sorted by fact ID.
    """
    chemical_sources = {c.id: c.source for c in plant.chemicals if c.source}

    def source(fact_id: str, object_id: str) -> str:
        return (
            plant.provenance.get(fact_id)
            or plant.provenance.get(object_id)
            or chemical_sources.get(object_id)
            or NOT_STATED
        )

    facts: list[PlantFact] = []
    for obj in _plant_objects(plant):
        object_id: str = getattr(obj, "id")  # noqa: B009
        skip = _NOT_FACTS | _NOT_FACTS_BY_TYPE.get(type(obj), set())
        dumped = obj.model_dump(mode="json")
        for field in type(obj).model_fields:
            if field in skip or getattr(obj, field) is None or getattr(obj, field) == []:
                continue
            fact_id = ids.fact_id(object_id, field)
            facts.append(
                PlantFact(
                    id=fact_id,
                    plant_record_id=plant_record_id,
                    value=dumped[field],
                    source=source(fact_id, object_id),
                )
            )
    for row in plant.operating:
        for limit in OPERATING_LIMITS:
            value = getattr(row, limit)
            if value is None:
                continue
            fact_id = ids.operating_fact_id(row.target_id, row.parameter, limit)
            facts.append(
                PlantFact(
                    id=fact_id,
                    plant_record_id=plant_record_id,
                    value=value,
                    source=source(fact_id, row.target_id),
                )
            )
    return sorted(facts, key=lambda f: f.id)


def not_stated_issues(facts: list[PlantFact]) -> list[Issue]:
    """One `source_not_stated` warning per fact with no source (P3)."""
    issues = []
    for fact in facts:
        if fact.source == NOT_STATED:
            object_id, _, field = fact.id.partition(".")
            issues.append(
                Issue(SOURCE_NOT_STATED, object_id, f"{fact.id}: no source stated for {field}")
            )
    return issues


@dataclass(frozen=True)
class StoredPlant:
    record: PlantRecord
    # the plant file exactly as uploaded
    raw: dict[str, Any]
    facts: list[PlantFact]
    sections: list[Section]


class PlantRepository:
    """The `plants`, `plant_facts` and `sections` tables."""

    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def add(self, record: PlantRecord, raw: Mapping[str, Any], facts: list[PlantFact]) -> None:
        """Store a plant and its facts; a record already stored is left as it is."""
        with self._sessions.begin() as session:
            if session.get(PlantRow, record.id) is not None:
                return
            session.add(
                PlantRow(
                    id=record.id,
                    plant_id=record.plant_id,
                    status=record.status.value,
                    plant_file=dict(raw),
                    confirmed_section_ids=list(record.confirmed_section_ids),
                )
            )
            session.flush()
            session.add_all(
                PlantFactRow(
                    plant_record_id=record.id, id=fact.id, value=fact.value, source=fact.source
                )
                for fact in facts
            )

    def get(self, record_id: str) -> StoredPlant | None:
        with self._sessions() as session:
            row = session.get(PlantRow, record_id)
            if row is None:
                return None
            facts = session.scalars(
                select(PlantFactRow).where(PlantFactRow.plant_record_id == record_id)
            ).all()
            sections = session.scalars(
                select(SectionRow)
                .where(SectionRow.plant_record_id == record_id)
                .order_by(SectionRow.position)
            ).all()
            return StoredPlant(
                record=_record(row),
                raw=row.plant_file,
                facts=sorted(
                    (
                        PlantFact(
                            id=f.id, plant_record_id=record_id, value=f.value, source=f.source
                        )
                        for f in facts
                    ),
                    key=lambda f: f.id,
                ),
                sections=[Section.model_validate(s.record) for s in sections],
            )

    def records(self) -> list[PlantRecord]:
        with self._sessions() as session:
            rows = session.scalars(select(PlantRow)).all()
            return sorted((_record(row) for row in rows), key=lambda r: r.id)

    def set_sections(self, record_id: str, sections: list[Section], status: PlantStatus) -> None:
        """Replace the plant's current sections; any confirmed set is cleared (P5)."""
        self._store_sections(record_id, sections, status, confirmed=[])

    def confirm(self, record_id: str, sections: list[Section]) -> None:
        """Store a confirmed section set; the plant moves to `sections_confirmed`."""
        self._store_sections(
            record_id,
            sections,
            PlantStatus.SECTIONS_CONFIRMED,
            confirmed=[s.id for s in sections],
        )

    def _store_sections(
        self, record_id: str, sections: list[Section], status: PlantStatus, confirmed: list[str]
    ) -> None:
        with self._sessions.begin() as session:
            row = session.get(PlantRow, record_id)
            if row is None:
                raise LookupError(f"no plant {record_id}")
            session.execute(delete(SectionRow).where(SectionRow.plant_record_id == record_id))
            session.add_all(
                SectionRow(
                    plant_record_id=record_id,
                    id=section.id,
                    position=position,
                    record=section.model_dump(mode="json"),
                )
                for position, section in enumerate(sections)
            )
            row.status = status.value
            row.confirmed_section_ids = confirmed


def _record(row: PlantRow) -> PlantRecord:
    return PlantRecord(
        id=row.id,
        plant_id=row.plant_id,
        plant_file=Plant.model_validate(row.plant_file),
        status=PlantStatus(row.status),
        confirmed_section_ids=list(row.confirmed_section_ids),
    )
