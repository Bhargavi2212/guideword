"""scripts/export_item.py (Phase 5 plan G14): one shortlist item as the API serves it, read-only."""

import hashlib
from pathlib import Path

import export_item
import make_fixtures
import pytest


@pytest.fixture(scope="module")
def store(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, object]]:
    """A store holding the fixture generator's $0 fake runs, and what the API served."""
    work = tmp_path_factory.mktemp("export")
    generator = make_fixtures.Generator(work)
    try:
        served = generator.build()
    finally:
        generator.client.close()
    return work / "fixtures.db", served


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_the_item_and_plant_are_the_apis_responses(store: tuple[Path, dict]) -> None:  # type: ignore[type-arg]
    path, served = store
    shortlist = served["shortlist.json"]
    item = next(i for i in shortlist["items"] if i["target_kind"] == "chain")
    before = _hash(path)
    data = export_item.export(path, shortlist["run_id"], item["target_id"])
    assert data["item"] == item
    assert data["plant_detail"]["plant_record_id"] == served["plant_detail.json"]["plant_record_id"]
    assert data["run_detail"]["run"]["id"] == shortlist["run_id"]
    assert data["source"] == {
        "store": path.name,
        "run_id": shortlist["run_id"],
        "target_id": item["target_id"],
    }
    assert _hash(path) == before


def test_a_target_not_on_the_shortlist_is_refused(store: tuple[Path, dict]) -> None:  # type: ignore[type-arg]
    path, served = store
    run_id = served["shortlist.json"]["run_id"]
    assert (
        export_item.main(
            [run_id, "f:not:there", "--store", str(path), "--out", str(path.parent / "x.json")]
        )
        == 1
    )
    assert not (path.parent / "x.json").exists()
