"""Determinism and completeness of sections and questions (spec 1.7)."""

import ast
import copy
import importlib
import inspect
import json
import pkgutil
import random
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import guideword.questions
import guideword.sections
from guideword.questions.build import build_questions
from guideword.reference import ReferenceSet, load_reference_set
from guideword.schema.plant import Plant
from guideword.schema.records import Question
from guideword.sections.rules import rule_cut

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
PLANTS = [EXAMPLE, *sorted((REPO / "cases" / "dev").glob("case_*.json"))]
RUN = "run:test"
# order is meaningful in these lists, so they are never shuffled
ORDERED = {"components", "steps"}
CLIENTS = {
    "openai",
    "tavily",
    "httpx",
    "requests",
    "live_call",
    "guideword.gateway",
    "guideword.tools",
}


@pytest.fixture(scope="module")
def ref() -> ReferenceSet:
    return load_reference_set()


def _load(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _output(data: dict[str, Any], ref: ReferenceSet) -> tuple[list[Any], list[Any]]:
    plant = Plant.model_validate(data)
    record = f"plant:{plant.plant_id}:0"
    sections = rule_cut(plant, record)
    questions = build_questions(plant, sections, ref, RUN)
    return [s.model_dump(mode="json") for s in sections], [
        q.model_dump(mode="json") for q in questions
    ]


def _shuffle(value: Any, rng: random.Random, key: str | None = None) -> Any:
    if isinstance(value, dict):
        return {k: _shuffle(v, rng, k) for k, v in value.items()}
    if isinstance(value, list):
        items = [_shuffle(v, rng) for v in value]
        if key not in ORDERED:
            rng.shuffle(items)
        return items
    return value


@pytest.mark.parametrize("path", PLANTS, ids=[p.stem for p in PLANTS])
def test_building_twice_is_identical(path: Path, ref: ReferenceSet) -> None:
    assert _output(_load(path), ref) == _output(_load(path), ref)


@pytest.mark.parametrize("path", PLANTS, ids=[p.stem for p in PLANTS])
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_shuffled_plant_lists_give_identical_output(
    path: Path, seed: int, ref: ReferenceSet
) -> None:
    """Every list shuffled, nested ones included, except a line's components and a procedure's
    steps. The record ID passed is the same (the shuffled file would hash differently)."""
    data = _load(path)
    shuffled = _shuffle(copy.deepcopy(data), random.Random(seed))
    assert shuffled != data
    assert _output(shuffled, ref) == _output(data, ref)


_CHILD = """
import json, sys
from pathlib import Path
from guideword.questions.build import build_questions
from guideword.reference import load_reference_set
from guideword.schema.plant import Plant
from guideword.sections.rules import rule_cut
plant = Plant.model_validate(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
sections = rule_cut(plant, f"plant:{plant.plant_id}:0")
questions = build_questions(plant, sections, load_reference_set(), "run:test")
print(json.dumps([[s.model_dump(mode="json") for s in sections],
                  [q.model_dump(mode="json") for q in questions]]))
"""


def test_two_processes_give_identical_output(ref: ReferenceSet) -> None:
    path = REPO / "cases" / "dev" / "case_g.json"
    runs = [
        subprocess.run(
            [sys.executable, "-c", _CHILD, str(path)],
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
        ).stdout
        for _ in range(2)
    ]
    assert runs[0] == runs[1]
    assert json.loads(runs[0]) == [list(part) for part in _output(_load(path), ref)]


def test_adding_plant_objects_never_removes_a_question(ref: ReferenceSet) -> None:
    """The builder is append-only: more plant gives a superset of questions."""
    data = _load(EXAMPLE)
    before = {q["id"] for q in _output(data, ref)[1]}
    data["chemicals"].append({"id": "WATER", "name": "water"})
    data["equipment"].append({"id": "T-2", "type": "tank", "location_id": "ROOF"})
    data["relief_devices"].append({"id": "PSV-9", "protects_id": "T-2"})
    data["planned_work"].append({"id": "W-9", "type": "lifting", "location_id": "ROOF"})
    after = {q["id"] for q in _output(data, ref)[1]}
    assert before < after


def _public_functions() -> list[tuple[str, Any]]:
    found = []
    for module_info in pkgutil.iter_modules(guideword.questions.__path__):
        module = importlib.import_module(f"guideword.questions.{module_info.name}")
        for name, fn in inspect.getmembers(module, inspect.isfunction):
            if fn.__module__ == module.__name__ and not name.startswith("_"):
                found.append((f"{module.__name__}.{name}", fn))
    return found


def test_no_public_function_removes_questions(ref: ReferenceSet) -> None:
    """Every public function in questions/ that takes a question list leaves it whole."""
    known = build_questions(Plant.model_validate(_load(EXAMPLE)), [], ref, RUN)
    assert known
    functions = _public_functions()
    assert "guideword.questions.build.build_questions" in dict(functions)
    for name, fn in functions:
        if "questions" not in inspect.signature(fn).parameters:
            continue
        given: list[Question] = list(known)
        result = fn(questions=given, **_other_arguments(fn))
        assert given == known, f"{name} changed its input list"
        returned = result if isinstance(result, list) else []
        if returned and isinstance(returned[0], Question):
            assert {q.id for q in known} <= {q.id for q in returned}, name


def _other_arguments(fn: Any) -> dict[str, Any]:
    """Empty values for a function's other required arguments."""
    arguments: dict[str, Any] = {}
    for param in inspect.signature(fn).parameters.values():
        if param.name != "questions" and param.default is inspect.Parameter.empty:
            arguments[param.name] = []
    return arguments


def _imports(package: Any) -> set[str]:
    names: set[str] = set()
    for path in Path(package.__path__[0]).glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names |= {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module)
    return names


@pytest.mark.parametrize("package", [guideword.sections, guideword.questions])
def test_sections_and_questions_import_no_client(package: Any) -> None:
    imported = _imports(package)
    assert not {
        name
        for name in imported
        for client in CLIENTS
        if name == client or name.startswith(f"{client}.")
    }
