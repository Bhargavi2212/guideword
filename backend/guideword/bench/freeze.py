"""What every benchmark script checks before it makes a call (Phase 6 spec P6-2, 6.4; plan G1,
G2a-G2c).

- **The checkout** (G2, G2c): the scripts run only from a clean checkout whose HEAD is exactly a
  `phase6-freeze*` tag, so later merges to `main` can't reach a run. Ignored files (the store,
  `bench/heldout/`) don't count as changes.
- **The code** (G2b): the imported `guideword` package and the script itself both lie inside
  that checkout; the shared `.venv`'s editable install points at the main checkout, so a run
  from the freeze worktree must set `PYTHONPATH` to the worktree's `backend` and `scripts`.
- **The ledger** (G2a): the main checkout's `budget/ledger.jsonl`, given explicitly, never one
  inside the freeze checkout (which would start empty and miss what was spent), and with its
  opening balance, so the budget guard sees the whole laptop spend.
- **The store** (G1): `guideword.db` and `guideword-demo.db` are refused by name.
"""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

FREEZE_TAG = "phase6-freeze"
REFUSED_STORES = ("guideword.db", "guideword-demo.db")


class FreezeRefused(RuntimeError):
    """A benchmark script may not run here."""


@dataclass(frozen=True)
class FreezeInfo:
    tag: str
    commit: str


def _git(root: Path, *args: str) -> str:
    try:
        done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError) as failed:
        raise FreezeRefused(f"git {' '.join(args)} failed in {root}") from failed
    return done.stdout.strip()


def _inside(path: Path, root: Path) -> bool:
    return path.resolve().is_relative_to(root.resolve())


def check_checkout(root: Path, *, package_file: Path, script_file: Path) -> FreezeInfo:
    """The checkout's freeze tag and commit, or FreezeRefused naming what's wrong."""
    top = Path(_git(root, "rev-parse", "--show-toplevel"))
    if top.resolve() != root.resolve():
        raise FreezeRefused(f"{root} is not the top of a git checkout")
    try:
        tag = _git(root, "describe", "--exact-match", "--tags", "HEAD")
    except FreezeRefused as untagged:
        raise FreezeRefused(f"HEAD is not a {FREEZE_TAG}* tag") from untagged
    if not tag.startswith(FREEZE_TAG):
        raise FreezeRefused(f"HEAD is tagged {tag}, not a {FREEZE_TAG}* tag")
    if _git(root, "status", "--porcelain"):
        raise FreezeRefused("the checkout is not clean: commit or remove the changes")
    if not _inside(package_file, root / "backend"):
        raise FreezeRefused(
            f"the guideword package was imported from outside {root}: set PYTHONPATH to the "
            "checkout's backend and scripts folders"
        )
    if not _inside(script_file, root):
        raise FreezeRefused(f"the script runs from outside {root}")
    return FreezeInfo(tag, _git(root, "rev-parse", "HEAD"))


def check_ledger(path: Path, root: Path) -> None:
    if not path.is_file():
        raise FreezeRefused(f"no ledger at {path}")
    if _inside(path, root):
        raise FreezeRefused(
            "the ledger is inside the freeze checkout: give the main checkout's budget/ledger.jsonl"
        )
    kinds = {
        json.loads(line).get("kind")
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    if "opening_balance" not in kinds:
        raise FreezeRefused(f"the ledger at {path} has no opening balance")


def check_store(path: Path) -> None:
    if path.name in REFUSED_STORES:
        raise FreezeRefused(f"refused: {path.name} is never a benchmark store (G1)")


def require_benchmark(
    root: Path, *, store: Path, ledger: Path, package_file: Path, script_file: Path
) -> FreezeInfo:
    """All the checks a benchmark script makes before its first call, in one place."""
    check_store(store)
    check_ledger(ledger, root)
    return check_checkout(root, package_file=package_file, script_file=script_file)


# what a later phase6-freeze* tag may change, compared with phase6-freeze (plan G2): the
# benchmark tooling only, never the pipeline, its API or its exports. The tests and the docs
# (the decisions log, the runbook) change nothing a run executes (decisions 2026-10-28).
ALLOWED_AFTER_FREEZE = ("backend/guideword/bench/", "scripts/", "backend/tests/", "docs/")


def freeze_diff(root: Path, new_tag: str, base_tag: str = FREEZE_TAG) -> list[str]:
    """The paths `new_tag` changes compared with `base_tag` that a later freeze tag may not."""
    if not new_tag.startswith(FREEZE_TAG):
        raise FreezeRefused(f"{new_tag} is not a {FREEZE_TAG}* tag")
    changed = _git(root, "diff", "--name-only", f"{base_tag}..{new_tag}").splitlines()
    return sorted(p for p in changed if p and not p.startswith(ALLOWED_AFTER_FREEZE))
