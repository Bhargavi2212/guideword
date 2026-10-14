"""Write contract/openapi.json from the FastAPI app (spec 0.8).

Run from the repo root:  python scripts/export_openapi.py
A test regenerates it in memory and fails if the committed file differs. The frontend
generates frontend/src/api/types.ts from it (npm run gen:types).
"""

import json
import sys
from pathlib import Path

from guideword.api.app import create_app
from guideword.settings import Settings

OUT = Path(__file__).resolve().parents[1] / "contract" / "openapi.json"


def render() -> str:
    app = create_app(settings=Settings(_env_file=None, guideword_mock=False))
    return json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    OUT.write_bytes(render().encode("utf-8"))
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
