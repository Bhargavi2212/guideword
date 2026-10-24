"""Export one shortlist item, as the API serves it, for a frontend test (Phase 5 plan G14).

  python scripts/export_item.py run:76f8ee0b5d1f078e <target ID>

Reads `guideword.db` with SQLite `mode=ro` (plan H15) through the real API: the run detail,
the run's shortlist item for the target, and its plant's detail (facts for the record drawer).
No model is ever called: the gateway refuses any request. Writes
`frontend/src/test/fixtures/wg_demo_item.json` (or `--out`). Nothing is invented: every field
is the API's response, unchanged.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi.testclient import TestClient
from guideword.api.app import create_app
from guideword.gateway.client import Gateway
from guideword.schema.enums import BudgetUse
from guideword.settings import Settings
from pydantic import SecretStr
from sqlalchemy.orm import Session, sessionmaker

REPO = Path(__file__).resolve().parents[1]
STORE = REPO / "guideword.db"
OUT = REPO / "frontend" / "src" / "test" / "fixtures" / "wg_demo_item.json"


class NoCalls(RuntimeError):
    """An export reads; it never asks a model."""


def no_gateway(sessions: sessionmaker[Session], use: BudgetUse) -> Gateway:
    raise NoCalls("export_item reads only; no gateway")


def read_only_url(store: Path) -> str:
    return f"sqlite:///file:{store.resolve().as_posix()}?mode=ro&uri=true"


def export(store: Path, run_id: str, target_id: str) -> dict[str, Any]:
    settings = Settings(
        _env_file=None,
        guideword_mock=False,
        database_url=read_only_url(store),
        internal_advance_secret=SecretStr(""),
    )
    with TestClient(create_app(settings=settings, gateway_factory=no_gateway)) as client:

        def get(path: str) -> Any:
            response = client.get(path)
            if response.status_code != 200:
                raise LookupError(f"GET {path}: {response.status_code} {response.text}")
            return response.json()

        run = get(f"/runs/{quote(run_id, safe='')}")
        shortlist = get(f"/runs/{quote(run_id, safe='')}/shortlist")
        items = [i for i in shortlist["items"] if i["target_id"] == target_id]
        if not items:
            raise LookupError(f"{target_id} is not on {run_id}'s shortlist")
        plant = get(f"/plants/{quote(run['run']['plant_record_id'], safe='')}")
    return {
        "source": {"store": store.name, "run_id": run_id, "target_id": target_id},
        "run_detail": run,
        "item": items[0],
        "plant_detail": plant,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_id")
    parser.add_argument("target_id")
    parser.add_argument("--store", type=Path, default=STORE)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    if not args.store.is_file():
        print(f"no store at {args.store}", file=sys.stderr)
        return 1
    try:
        data = export(args.store, args.run_id, args.target_id)
    except LookupError as missing:
        print(f"refused: {missing}", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
