"""Precedent search by code (Phase 4 spec 4.3 steps 1-3; plan PR 3, Q17, G20).

- `query_for`: the search query, built by code from the line alone: each finding's cause text,
  its question's guideword and parameter (or chemicals), the scenario's equipment types and the
  names of the chemicals it holds. No model writes it.
- `blocked`: a plant's block terms, each matching as a whole word or phrase on word boundaries
  at both ends, case-insensitive, in any field or the URL (Q17). Applied before anything else.
- `bm25`: Okapi BM25 over each row's title, summary, chemicals, equipment types and mechanism
  keywords; ties broken by row ID, so the same query always gives the same candidates.

The block list of a plant is `<plant_id>.block.txt` under `cases/demo/` or `cases/dev/`; a
plant with none (an uploaded plant) gets none, and the evidence pass records that.
"""

import hashlib
import math
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from guideword.reference import ReferenceSet
from guideword.reference.precedents import PrecedentRow
from guideword.schema.enums import QuestionKind
from guideword.schema.ids import PLANT_ID_PATTERN, parse_question_id
from guideword.schema.plant import Plant
from guideword.schema.records import Finding, Section

DEFAULT_CASES_DIR = Path(__file__).resolve().parents[3] / "cases"
BLOCK_LIST_DIRS = ("demo", "dev")
BLOCK_SUFFIX = ".block.txt"
# Okapi BM25's usual parameters (Robertson and Zaragoza, "The Probabilistic Relevance
# Framework: BM25 and Beyond", 2009): term-frequency saturation and length normalisation
BM25_K1 = 1.2
BM25_B = 0.75

_TOKEN = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


# --- block terms ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class BlockList:
    path: Path
    terms: tuple[str, ...]
    # SHA-256 of the file bytes, recorded on the evidence pass event
    version: str


def load_block_terms(path: Path) -> tuple[tuple[str, ...], str]:
    """One term per line; blank lines and `#` comments are skipped."""
    data = path.read_bytes()
    lines = (line.strip() for line in data.decode("utf-8").splitlines())
    terms = tuple(line for line in lines if line and not line.startswith("#"))
    return terms, hashlib.sha256(data).hexdigest()


def block_list_for(plant_id: str, cases_dir: Path | None = None) -> BlockList | None:
    if not re.fullmatch(PLANT_ID_PATTERN, plant_id):
        raise ValueError(f"not a plant ID: {plant_id!r}")
    root = cases_dir if cases_dir is not None else DEFAULT_CASES_DIR
    for folder in BLOCK_LIST_DIRS:
        path = root / folder / f"{plant_id}{BLOCK_SUFFIX}"
        if path.is_file():
            terms, version = load_block_terms(path)
            return BlockList(path, terms, version)
    return None


def _pattern(terms: Sequence[str]) -> re.Pattern[str] | None:
    if not terms:
        return None
    alternatives = "|".join(re.escape(term) for term in terms)
    return re.compile(rf"\b(?:{alternatives})\b", re.IGNORECASE)


def blocked(texts: Iterable[str], terms: Sequence[str]) -> bool:
    """True when any text holds any term as a whole word or phrase (Q17)."""
    pattern = _pattern(terms)
    return pattern is not None and any(pattern.search(text) for text in texts)


def row_texts(row: PrecedentRow) -> list[str]:
    """Every field of an index row, and its URL, as the block check reads them."""
    return [
        row.id,
        row.title,
        row.date,
        row.country,
        row.company,
        row.location,
        *row.chemicals,
        *row.equipment_types,
        *row.mechanism_keywords,
        row.summary,
        row.url,
        row.source,
    ]


# --- BM25 ----------------------------------------------------------------------------------------


def _document(row: PrecedentRow) -> list[str]:
    fields = [row.title, row.summary, *row.chemicals, *row.equipment_types]
    return tokens(" ".join([*fields, *row.mechanism_keywords]))


def bm25(rows: Sequence[PrecedentRow], query: str, k: int) -> list[tuple[PrecedentRow, float]]:
    """The top `k` rows sharing a term with the query, by BM25 score, then row ID."""
    docs = [_document(row) for row in rows]
    if not docs:
        return []
    terms = set(tokens(query))
    average = sum(len(d) for d in docs) / len(docs) or 1.0
    frequency = Counter(term for d in docs for term in set(d))
    scored: list[tuple[PrecedentRow, float]] = []
    for row, doc in zip(rows, docs, strict=True):
        counts = Counter(doc)
        score = 0.0
        for term in terms & set(counts):
            n = frequency[term]
            idf = math.log((len(docs) - n + 0.5) / (n + 0.5) + 1)
            tf = counts[term]
            norm = tf + BM25_K1 * (1 - BM25_B + BM25_B * len(doc) / average)
            score += idf * tf * (BM25_K1 + 1) / norm
        if score > 0:
            scored.append((row, score))
    scored.sort(key=lambda pair: (-pair[1], pair[0].id))
    return scored[:k]


# --- the query -----------------------------------------------------------------------------------


def query_for(
    links: Sequence[tuple[Finding, Section | None]], plant: Plant, ref: ReferenceSet
) -> str:
    """The query for a line: its lead finding, or a chain's finding links, each with its
    section. Words in a fixed order, each once; no IDs."""
    causes = {row.id: row.cause for row in ref.causes}
    equipment = {e.id: e for e in plant.equipment}
    chemicals = {c.id: c.name for c in plant.chemicals}
    words: list[str] = []
    for found, section in links:
        words += tokens(causes.get(found.cause_id) or found.cause_text or "")
        parsed = parse_question_id(found.question_id)
        named: list[str] = []
        if parsed.kind == QuestionKind.MATRIX:
            words += tokens(" ".join(parsed.parts[1:]))
        else:
            named = [p for p in parsed.parts if p in chemicals]
        objects = [*(section.object_ids if section else ()), *found.failing_component_ids]
        items = [equipment[o] for o in objects if o in equipment]
        words += tokens(" ".join(item.type.replace("_", " ") for item in items))
        held = named + [c for item in items for c in item.contents]
        words += tokens(" ".join(chemicals[c] for c in held if c in chemicals))
    return " ".join(dict.fromkeys(words))
