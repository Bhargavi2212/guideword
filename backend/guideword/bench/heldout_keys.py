"""The held-out answer keys in the template's shape (Phase 6 spec P6-9; `docs/case-template.md` §4).

One record per case, in a list or a mapping of case to record. Each is validated with a model of
the template's fields. A record missing a field stops the scorer: the error names the fields it
found and the ones it lacks, never a value (P6-9). Only Bhargavi's scripts read the real keys.
"""

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from guideword.bench.scoring import case_letter

FIELDS = (
    "case_id",
    "root_cause",
    "component_ids",
    "cause_ids",
    "match_phrases",
    "consequence",
    "missed_by_original_review",
    "multi_failure",
    "source",
)


class KeyFieldsMissing(ValueError):
    """A key record lacks a template field; the message names fields only, never values."""


class HeldoutKey(BaseModel):
    model_config = ConfigDict(extra="allow")

    case_id: str
    root_cause: str
    component_ids: list[str]
    cause_ids: list[str]
    match_phrases: list[str]
    consequence: str
    missed_by_original_review: str
    multi_failure: bool
    # the template gives an object (kind, reference, pages); a plain string is accepted too
    source: Any


def _records(data: Any) -> Iterable[Any]:
    if isinstance(data, list):
        return data
    if isinstance(data, Mapping):
        return data.values()
    raise KeyFieldsMissing("the keys file is neither a list nor a mapping of key records")


def letter_of(case_id: str) -> str:
    """`case_k`, `case_k_tank` and `K` are all case `k`."""
    name = case_id if case_id.lower().startswith("case_") else f"case_{case_id}"
    return case_letter(name.lower())


def load_heldout_keys(path: Path) -> dict[str, HeldoutKey]:
    keys: dict[str, HeldoutKey] = {}
    for record in _records(json.loads(path.read_text(encoding="utf-8"))):
        found = sorted(record) if isinstance(record, Mapping) else []
        missing = [f for f in FIELDS if f not in found]
        if missing:
            raise KeyFieldsMissing(f"a key lacks the template's fields {missing}; it has {found}")
        try:
            key = HeldoutKey.model_validate(record)
        except ValidationError as invalid:
            wrong = sorted({str(e["loc"][0]) for e in invalid.errors() if e["loc"]})
            raise KeyFieldsMissing(
                f"a key's fields {wrong} don't have the template's types"
            ) from None
        keys[letter_of(key.case_id)] = key
    return keys
