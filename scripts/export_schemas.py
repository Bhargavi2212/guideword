"""Write the plant schema, every record schema and the enums to contract/schemas/ (spec 0.5).

Run from the repo root:  python scripts/export_schemas.py
A test regenerates these in memory and fails if the committed files differ.
"""

import json
import re
import sys
from enum import StrEnum
from pathlib import Path

from guideword.schema import enums
from guideword.schema.plant import Plant
from guideword.schema.records import RECORD_MODELS

OUT = Path(__file__).resolve().parents[1] / "contract" / "schemas"


def file_stem(class_name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", class_name).lower()


def _render(schema: object) -> str:
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _enum_schema() -> dict[str, object]:
    defs = {
        name: {"title": name, "type": "string", "enum": [member.value for member in obj]}
        for name, obj in vars(enums).items()
        if isinstance(obj, type) and issubclass(obj, StrEnum) and obj is not StrEnum
    }
    return {"title": "Guideword enums", "$defs": defs}


def render_all() -> dict[str, str]:
    """File name -> exact file text."""
    files = {"plant.schema.json": _render(Plant.model_json_schema())}
    for model in RECORD_MODELS:
        files[f"{file_stem(model.__name__)}.schema.json"] = _render(model.model_json_schema())
    files["enums.schema.json"] = _render(_enum_schema())
    return files


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    files = render_all()
    for stale in OUT.glob("*.json"):
        if stale.name not in files:
            stale.unlink()
            print(f"removed {stale.name}")
    for name, text in files.items():
        (OUT / name).write_bytes(text.encode("utf-8"))
    print(f"wrote {len(files)} schemas to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
