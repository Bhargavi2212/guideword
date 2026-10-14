"""contract/schemas/ matches the models (spec 0.5): the test regenerates and compares."""

import json
from pathlib import Path

import export_schemas

from guideword.schema import enums
from guideword.schema.records import RECORD_MODELS

SCHEMAS = Path(__file__).resolve().parents[3] / "contract" / "schemas"


def test_committed_schemas_match_the_models() -> None:
    expected = export_schemas.render_all()
    on_disk = {
        p.relative_to(SCHEMAS).as_posix(): p.read_text(encoding="utf-8")
        for p in SCHEMAS.rglob("*.json")
    }
    assert set(on_disk) == set(expected), "run: python scripts/export_schemas.py"
    for name, text in expected.items():
        assert on_disk[name] == text, f"{name} is stale; run: python scripts/export_schemas.py"


def test_plant_schema_is_named_as_in_project_md() -> None:
    assert "plant.schema.json" in export_schemas.render_all()


def test_one_schema_per_record_model() -> None:
    names = set(export_schemas.render_all())
    for model in RECORD_MODELS:
        assert f"{export_schemas.file_stem(model.__name__)}.schema.json" in names


def test_api_models_are_exported() -> None:
    from guideword.api import models as api

    names = set(export_schemas.render_all())
    for model in [*api.RESPONSE_FIXTURES, *export_schemas.API_REQUEST_MODELS]:
        assert f"api/{export_schemas.file_stem(model.__name__)}.schema.json" in names


def test_enums_are_exported() -> None:
    schema = json.loads(export_schemas.render_all()["enums.schema.json"])
    assert schema["$defs"]["NoFlow"]["enum"] == [v.value for v in enums.NoFlow]
    assert schema["$defs"]["RunStatus"]["enum"] == [v.value for v in enums.RunStatus]


def test_output_is_stable_lf_json() -> None:
    for text in export_schemas.render_all().values():
        assert "\r" not in text
        assert text.endswith("}\n")
        assert json.loads(text)


def test_file_stem() -> None:
    assert export_schemas.file_stem("PlantRecord") == "plant_record"
    assert export_schemas.file_stem("LopaRecord") == "lopa_record"
    assert export_schemas.file_stem("Run") == "run"
