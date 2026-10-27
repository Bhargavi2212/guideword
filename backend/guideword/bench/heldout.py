"""The held-out folder before anyone reads it (Phase 6 spec 6.1, P6-1, P6-3; plan PR 1, G9, G10).

Bhargavi runs `scripts/heldout_verify.py` on the folder; nothing here is run on held-out files in
this repo's tests (CLAUDE.md §5). What it reports names files, counts and field names only,
never a line of any file:

- **Seals.** `SEALS.txt` lists each file's SHA-256 in `sha256sum`'s format (`<hex>  <path>`, or
  `<hex> *<path>`). Every listed file is hashed again; a missing or changed file fails, and so
  does an unlisted package or key or any unlisted file inside `cases/` or `keys/`. Plant files
  made after sealing (P6-12) are listed apart and frozen, never sealed; any other unlisted file
  outside `cases/` and `keys/` is reported, not checked (2026-10-26). The folder's own `.git/`
  and `SEALS.txt` are not files of the cases.
- **Inventory.** Each sealed file is classified by its name (plan G9): a package
  `case_<letter>_*.md`, a plant file `case_<letter>*.json`, the keys `keys/answer_keys.json` or
  one file per case, `keys/case_<letter>*.json`;
  anything else is "unclassified". The keys' field names are listed, never their values.
- **Plant files.** Each goes through `schema.validate.validate_plant`, whose issues name an
  object ID and a field. When every seal matches and every plant file validates, the plant files'
  hashes are written for `bench/heldout-frozen.txt` (P6-3 step 2).
"""

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from guideword.reference import ReferenceSet
from guideword.schema.validate import Issue, validate_plant

SEALS_FILE = "SEALS.txt"
KEYS_FILE = "keys/answer_keys.json"
# `sha256sum` writes "<hex>  <path>" (text mode) or "<hex> *<path>" (binary mode); the held-out
# folder's lines add a third column, the seal date, after a tab or two spaces
_SEAL_LINE = re.compile(r"^([0-9a-fA-F]{64}) [ *](.+)$")
_COLUMN = re.compile(r"\t|\s{2,}")
_KEY_FILE = re.compile(r"^keys/case_[a-z][^/]*\.json$", re.IGNORECASE)
_PACKAGE = re.compile(r"^case_[a-z]_.+\.md$", re.IGNORECASE)
_PLANT = re.compile(r"^case_[a-z][^/]*\.json$", re.IGNORECASE)

Kind = Literal["package", "plant", "keys", "unclassified"]
KINDS: tuple[Kind, ...] = ("package", "plant", "keys", "unclassified")


@dataclass(frozen=True)
class SealCheck:
    listed: int
    ok: int
    missing: list[str] = field(default_factory=list)
    # unlisted packages or keys, or any unlisted file inside cases/ or keys/: these fail
    unlisted: list[str] = field(default_factory=list)
    mismatched: list[str] = field(default_factory=list)
    # line numbers in SEALS.txt that are not a seal (their text is never shown)
    bad_lines: list[int] = field(default_factory=list)
    # plant files made after sealing (P6-12): validated and frozen apart, never sealed
    unsealed_plants: list[str] = field(default_factory=list)
    # other files outside cases/ and keys/ (the folder's README, template, seal script, log):
    # reported, not checked, not a failure (Bhargavi, 2026-10-26)
    unsealed_other: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not (self.missing or self.unlisted or self.mismatched or self.bad_lines)


@dataclass(frozen=True)
class Inventory:
    counts: dict[str, int]
    unclassified: list[str]
    # the keys file's field names, sorted; never a value
    key_fields: list[str]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_seals(text: str) -> tuple[dict[str, str], list[int]]:
    """The sealed paths with their hashes, and the numbers of the lines that are not a seal."""
    seals: dict[str, str] = {}
    bad: list[int] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        match = _SEAL_LINE.match(line.rstrip("\r"))
        if match is None:
            bad.append(number)
            continue
        path = _COLUMN.split(match.group(2).strip())[0]
        seals[PurePosixPath(path.replace("\\", "/")).as_posix()] = match.group(1).lower()
    return seals, bad


SEALED_FOLDERS = ("cases/", "keys/")


def case_files(folder: Path) -> list[str]:
    return sorted(
        path.relative_to(folder).as_posix()
        for path in folder.rglob("*")
        if path.is_file()
        and ".git" not in path.relative_to(folder).parts
        and path.relative_to(folder).as_posix() != SEALS_FILE
    )


def check_seals(folder: Path) -> SealCheck:
    seals_path = folder / SEALS_FILE
    if not seals_path.is_file():
        raise FileNotFoundError(f"no {SEALS_FILE} in the folder")
    seals, bad = read_seals(seals_path.read_text(encoding="utf-8"))
    present = set(case_files(folder))
    missing = sorted(p for p in seals if p not in present)
    extra = sorted(p for p in present if p not in seals)
    plants = [p for p in extra if classify(p) == "plant"]
    unlisted = [
        p
        for p in extra
        if p not in plants and (classify(p) != "unclassified" or p.startswith(SEALED_FOLDERS))
    ]
    other = [p for p in extra if p not in plants and p not in unlisted]
    mismatched = sorted(p for p in seals if p in present and _sha256(folder / p) != seals[p])
    ok = len(seals) - len(missing) - len(mismatched)
    return SealCheck(len(seals), ok, missing, unlisted, mismatched, bad, plants, other)


def classify(path: str) -> Kind:
    if path == KEYS_FILE or _KEY_FILE.match(path):
        return "keys"
    name = PurePosixPath(path).name
    if _PACKAGE.match(name):
        return "package"
    if _PLANT.match(name) and not path.startswith("keys/"):
        return "plant"
    return "unclassified"


def _key_fields(data: Any) -> list[str]:
    """Field names of the key records: a list of records, or a mapping of case to record."""
    records: Iterable[Any]
    if isinstance(data, list):
        records = data
    elif isinstance(data, Mapping) and all(isinstance(v, Mapping) for v in data.values()):
        records = data.values()
    else:
        records = [data]
    return sorted({str(k) for r in records if isinstance(r, Mapping) for k in r})


def inventory(folder: Path, seals: Mapping[str, str]) -> Inventory:
    kinds = {path: classify(path) for path in seals}
    counts: dict[str, int] = {kind: sum(1 for k in kinds.values() if k == kind) for kind in KINDS}
    names: set[str] = set()
    for path in sorted(p for p, k in kinds.items() if k == "keys"):
        if (folder / path).is_file():
            names |= set(_key_fields(json.loads((folder / path).read_text(encoding="utf-8"))))
    fields = sorted(names)
    unclassified = sorted(p for p, k in kinds.items() if k == "unclassified")
    return Inventory(counts, unclassified, fields)


def plant_files(seals: Mapping[str, str]) -> list[str]:
    return sorted(p for p in seals if classify(p) == "plant")


def validate_plants(
    folder: Path, paths: Iterable[str], ref: ReferenceSet
) -> dict[str, list[Issue]]:
    """Each plant file's errors (an empty list when it validates)."""
    return {
        path: validate_plant(json.loads((folder / path).read_text(encoding="utf-8")), ref).errors
        for path in paths
    }


def frozen_lines(folder: Path, paths: Iterable[str]) -> str:
    """The plant files' hashes in `sha256sum`'s format, for `bench/heldout-frozen.txt`."""
    return "".join(f"{_sha256(folder / p)}  {p}\n" for p in sorted(paths))


def seal_info(folder: Path) -> tuple[int, str]:
    """`SEALS.txt`'s size in bytes and its modification time (UTC), for the P6-1 row (G10)."""
    stat = (folder / SEALS_FILE).stat()
    when = datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat().replace("+00:00", "Z")
    return stat.st_size, when
