"""The deployed site (deploy plan D4): the Vercel function serves the committed WG export with no
key, the rewrites send every API route to it, and its requirements are the backend's pins."""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from guideword.api import models as api
from guideword.api.app import create_app
from guideword.settings import Settings

REPO = Path(__file__).resolve().parents[2]
SITE = json.loads((REPO / "deploy" / "site.json").read_text(encoding="utf-8"))
KEYS = ("NEBIUS_API_KEY", "TAVILY_API_KEY", "INTERNAL_ADVANCE_SECRET")


def _entry(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """api/index.py, imported as Vercel imports it, with no key in the environment."""
    for key in [*KEYS, *SITE["env"]]:
        # set, then delete: monkeypatch records the key, so the entry's setdefault is undone after
        monkeypatch.setenv(key, "")
        monkeypatch.delenv(key)
    # the deployment has no .env: the settings must not read the developer's
    monkeypatch.chdir(REPO / "deploy")
    spec = importlib.util.spec_from_file_location("site_entry", REPO / "api" / "index.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "site_entry", module)
    spec.loader.exec_module(module)
    return module


def test_the_entry_serves_the_wg_demo_with_no_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    entry = _entry(monkeypatch)
    settings: Settings = entry.settings
    assert settings.nebius_api_key.get_secret_value() == ""
    assert settings.tavily_api_key.get_secret_value() == ""
    assert settings.guideword_env == "hosted"
    client = TestClient(entry.app)
    response = client.get("/demo")
    assert response.status_code == 200, response.text
    demo = api.DemoResponse.model_validate(response.json())
    wg = SITE["env"]["GUIDEWORD_DEMO_RUNS"][0]
    assert demo.run.run.id == wg["run_id"]
    assert demo.label.kind == "recorded" and demo.label.note
    assert demo.start_target_id == wg["start_target_id"]
    assert [r.run_id for r in demo.runs] == [
        r["run_id"] for r in SITE["env"]["GUIDEWORD_DEMO_RUNS"]
    ]
    rank = next(i.rank for i in demo.shortlist.items if i.target_id == wg["start_target_id"])
    assert demo.runs[0].banner == wg["banner"].replace("{start_rank}", str(rank))
    run = quote(demo.run.run.id, safe="")
    target = quote(wg["start_target_id"], safe="")
    assert client.get(f"/runs/{run}/records/{target}").status_code == 200
    override = client.post(
        f"/runs/{run}/overrides",
        json={"target_id": "x", "action": "accept", "new_value": None, "reason": "r", "by": "B"},
    )
    assert override.status_code == 403


def test_vercel_rewrites_name_every_public_api_prefix() -> None:
    vercel = json.loads((REPO / "vercel.json").read_text(encoding="utf-8"))
    rewritten = {r["source"].split("/")[1] for r in vercel["rewrites"]}
    app = create_app(settings=Settings(_env_file=None, guideword_mock=True))
    prefixes = {
        route.path.split("/")[1]
        for route in app.routes
        if not route.path.startswith(("/openapi", "/docs", "/redoc", "/internal"))
    }
    assert rewritten == prefixes
    assert all(r["destination"] == "/api/index.py" for r in vercel["rewrites"])


def test_the_function_bundles_its_data_folders() -> None:
    vercel = json.loads((REPO / "vercel.json").read_text(encoding="utf-8"))
    bundled = vercel["functions"]["api/index.py"]["includeFiles"]
    for folder in ("backend/guideword", "config", "prompts", "reference", "deploy"):
        assert folder in bundled, folder
    for recorded in SITE["env"]["GUIDEWORD_RECORDED_DIRS"]:
        assert recorded in bundled, recorded


def test_the_function_requirements_are_the_backends_pins() -> None:
    def pins(path: Path) -> set[str]:
        return {
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if "==" in line and not line.strip().startswith("#")
        }

    assert pins(REPO / "requirements.txt") == pins(REPO / "backend" / "requirements.txt")


# --- review plan R5: D and G on the site ---------------------------------------------------------


def test_the_site_offers_wg_then_d_then_g_and_serves_each_with_no_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = _entry(monkeypatch)
    client = TestClient(entry.app)
    demo = api.DemoResponse.model_validate(client.get("/demo").json())
    wanted = [r["run_id"] for r in SITE["env"]["GUIDEWORD_DEMO_RUNS"]]
    assert [r.run_id for r in demo.runs] == wanted and len(wanted) == 3
    assert demo.run.run.id == wanted[0]  # WG stays first and the default
    for run in demo.runs:
        path = f"/runs/{quote(run.run_id, safe='')}"
        for rest in ("", "/shortlist", "/events", "/worksheet", "/coverage", "/sections"):
            assert client.get(path + rest).status_code == 200, (run.run_id, rest)
        detail = api.RunDetail.model_validate(client.get(path).json())
        assert detail.label.kind == "recorded"
        refused = client.post(
            f"{path}/overrides",
            json={
                "target_id": "x",
                "action": "accept",
                "new_value": None,
                "reason": "r",
                "by": "B",
            },
        )
        assert refused.status_code == 403


def test_d_and_g_have_their_banners_and_no_start_line_or_found_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = _entry(monkeypatch)
    demo = api.DemoResponse.model_validate(TestClient(entry.app).get("/demo").json())
    by_plant = {r.plant_id: r for r in demo.runs}
    for plant in ("case_d", "case_g"):
        run = by_plant[plant]
        assert run.start_target_id is None
        assert run.banner and "development case" in run.banner
        assert "found" not in run.banner.lower() and "accident" not in run.banner.lower()
