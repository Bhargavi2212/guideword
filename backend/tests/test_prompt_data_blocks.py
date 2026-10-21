"""Every prompt slot that carries plant, reference or model text is written with `as_data`
(CLAUDE.md §3: plant text, tool results and model output are data, never instructions).

A structural guard over the source, so a slot added later is covered too: every
`render(body, values)` call in a module that imports `render` from `guideword.gateway.prompts`
must pass its values as a dict literal (or a name bound to one in the same function), and each
value must be an `as_data(...)` call, unless its slot is in `CODE_ONLY` with the reason why it
can hold no outside text. A slot that cannot be read this way fails too."""

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
ROOTS = [REPO / "backend" / "guideword", REPO / "scripts"]

# slot -> why its value can hold no plant, reference or model text
CODE_ONLY = {
    "dispatch_max_question_ids": "an integer from caps.yaml",
    "unsure_reanswers_left": "an integer computed by code",
    "max_added_questions": "an integer from caps.yaml",
    "max_hypotheses": "an integer from caps.yaml",
    "max_chains": "an integer from caps.yaml (connector_max_chains)",
    "count": "the number of targets sent, counted by code",
    "handles": "the handles code numbered (L1, C1, ...), joined by code",
    "question_kinds": "names from the QuestionKind enum, joined by code",
    # kept verbatim so test 5A on E and F sees what it saw on D and G; test5a.py refuses a
    # package holding its block's tags instead (R50 review, G22)
    "package": "the 5A source package as written; tags in it are refused",
}


def _imports_render(tree: ast.Module) -> bool:
    return any(
        isinstance(node, ast.ImportFrom)
        and node.module == "guideword.gateway.prompts"
        and any(alias.name == "render" for alias in node.names)
        for node in ast.walk(tree)
    )


def _bound_dict(function: ast.AST, name: str) -> dict[str, ast.expr] | None:
    """`name = {...}` in the function, plus later `name["slot"] = value` assignments."""
    slots: dict[str, ast.expr] | None = None
    for node in ast.walk(function):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == name:
                if not isinstance(node.value, ast.Dict):
                    return None
                slots = dict(_literal(node.value) or {})
            elif (
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
                and target.value.id == name
                and isinstance(target.slice, ast.Constant)
                and slots is not None
            ):
                slots[str(target.slice.value)] = node.value
    return slots


def _literal(node: ast.Dict) -> dict[str, ast.expr] | None:
    out: dict[str, ast.expr] = {}
    for key, value in zip(node.keys, node.values, strict=True):
        if not isinstance(key, ast.Constant):
            return None
        out[str(key.value)] = value
    return out


def _is_as_data(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "as_data"
    )


def problems(source: str, where: str) -> list[str]:
    tree = ast.parse(source)
    if not _imports_render(tree):
        return []
    found: list[str] = []
    functions = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]
    for function in functions:
        for call in ast.walk(function):
            if not (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == "render"
            ):
                continue
            line = f"{where}:{call.lineno}"
            if len(call.args) != 2:
                found.append(f"{line}: render() without (body, values)")
                continue
            values = call.args[1]
            slots = (
                _literal(values)
                if isinstance(values, ast.Dict)
                else _bound_dict(function, values.id)
                if isinstance(values, ast.Name)
                else None
            )
            if slots is None:
                found.append(f"{line}: the values are not a dict literal this test can read")
                continue
            for slot, value in slots.items():
                if slot not in CODE_ONLY and not _is_as_data(value):
                    found.append(f"{line}: slot {slot!r} is not written with as_data")
    return found


def _sources() -> list[Path]:
    return sorted(p for root in ROOTS for p in root.rglob("*.py"))


def test_every_data_slot_is_written_with_as_data() -> None:
    found = [
        p
        for path in _sources()
        for p in problems(path.read_text(encoding="utf-8"), path.relative_to(REPO).as_posix())
    ]
    assert found == []


def test_the_guard_sees_render_calls_at_all() -> None:
    """The scan reaches the five prompt builders, so an empty result means something."""
    using = [
        path.name for path in _sources() if _imports_render(ast.parse(path.read_text("utf-8")))
    ]
    assert {"step.py", "run.py", "severity.py", "loop.py", "test5a.py"} <= set(using)


IMPORT = "from guideword.gateway.prompts import as_data, render\nimport json\n"


@pytest.mark.parametrize(
    "body",
    [
        'def f(x):\n    return render("b", {"plant": json.dumps(x)})\n',
        'def f(x):\n    values = {"plant": as_data(x)}\n    values["notes"] = str(x)\n'
        '    return render("b", values)\n',
        'def f(x):\n    return render("b", make(x))\n',
    ],
)
def test_a_slot_that_skips_as_data_fails_the_guard(body: str) -> None:
    assert problems(IMPORT + body, "new.py")


def test_as_data_and_code_only_slots_pass_the_guard() -> None:
    body = (
        'def f(x, n):\n    values = {"plant": as_data(x)}\n    values["max_hypotheses"] = str(n)\n'
        '    return render("b", values)\n'
    )
    assert problems(IMPORT + body, "new.py") == []
