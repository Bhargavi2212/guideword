"""Copy a run store to a new file (Phase 5 plan G8, G9, H15). No calls; Bhargavi runs it.

  python scripts/copy_store.py guideword.db guideword-demo.db
  python scripts/copy_store.py guideword.db guideword-scratch.db

`guideword.db` is the untouched record: the source is opened read-only (SQLite `mode=ro`)
and copied with SQLite's backup API, so nothing can write it. The target must not exist,
so a copy never replaces a store that may hold overrides or runs.
"""

import argparse
import sqlite3
import sys
from collections.abc import Iterator, Sequence
from contextlib import closing, contextmanager
from pathlib import Path


@contextmanager
def read_only(path: Path) -> Iterator[sqlite3.Connection]:
    """A connection to `path` that refuses every write."""
    uri = f"{path.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as db:
        yield db


def copy_store(source: Path, target: Path) -> Path:
    """Copy `source` to `target`; refuses a missing source and an existing target."""
    if not source.is_file():
        raise FileNotFoundError(f"no store at {source}")
    if target.exists():
        raise FileExistsError(f"{target} already exists; nothing was copied")
    try:
        with read_only(source) as src, closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
    except sqlite3.Error:
        target.unlink(missing_ok=True)
        raise
    return target


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path, help="the store to copy, e.g. guideword.db")
    parser.add_argument("target", type=Path, help="the new file, e.g. guideword-demo.db")
    args = parser.parse_args(argv)
    try:
        copy_store(args.source, args.target)
    except (FileNotFoundError, FileExistsError) as error:
        print(error, file=sys.stderr)
        return 1
    print(f"copied {args.source} to {args.target} (source opened read-only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
