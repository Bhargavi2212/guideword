"""Only the allowed files import openai, tavily or httpx (spec 0.3, CLAUDE.md section 3).

The allow-list below is a constant. Changing it is a stop-and-ask change.
"""

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Phase 0. From Phase 2, backend/guideword/gateway/** (openai, httpx) and
# backend/guideword/tools/** (tavily, httpx) are added.
ALLOWED: dict[str, tuple[str, ...]] = {
    "openai": ("scripts/live_call.py",),
    "tavily": ("scripts/live_call.py",),
    "httpx": ("scripts/live_call.py", "backend/tests/**"),
}
SKIP_PARTS = {".venv", "node_modules", "__pycache__", ".mypy_cache", ".ruff_cache"}


def _allowed(relative: str, patterns: tuple[str, ...]) -> bool:
    for pattern in patterns:
        if pattern.endswith("/**"):
            if relative.startswith(pattern[:-2]):
                return True
        elif relative == pattern:
            return True
    return False


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


def violations(root: Path) -> list[str]:
    found = []
    for top in ("backend", "scripts"):
        for path in sorted((root / top).rglob("*.py")):
            if SKIP_PARTS & set(path.parts):
                continue
            relative = path.relative_to(root).as_posix()
            for module in _imports(path) & set(ALLOWED):
                if not _allowed(relative, ALLOWED[module]):
                    found.append(f"{relative} imports {module}")
    return found


def test_only_allowed_files_import_http_clients() -> None:
    assert violations(REPO) == []


def test_live_call_is_the_one_paid_caller() -> None:
    assert {"openai", "tavily"} <= _imports(REPO / "scripts" / "live_call.py")


def test_a_forbidden_import_fails(tmp_path: Path) -> None:
    (tmp_path / "backend" / "guideword").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "backend" / "guideword" / "sneaky.py").write_text("import openai\n")
    (tmp_path / "scripts" / "helper.py").write_text("from tavily import TavilyClient\n")
    (tmp_path / "scripts" / "live_call.py").write_text("import openai\nimport httpx\n")
    (tmp_path / "backend" / "tests").mkdir()
    (tmp_path / "backend" / "tests" / "test_x.py").write_text("import httpx\n")
    assert violations(tmp_path) == [
        "backend/guideword/sneaky.py imports openai",
        "scripts/helper.py imports tavily",
    ]
