"""D–G's stored run IDs stay unchanged (connector/v2 plan, Q5, approved 2026-10-21).

The post-step prompts and caps leave the run-ID hash for new runs only: the hash covers what a
run stores, so the Phase 2 runs D–G, whose stored caps hold `lopa_top_n`, rebuild exactly their
stored IDs from their stored inputs. The fixture is their stored inputs, copied from the run
store; changing how the run ID is built (not what a new run stores) would fail here."""

import json
from pathlib import Path

import pytest

from guideword.schema import ids

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "dev_run_inputs.json"
RUNS = json.loads(FIXTURE.read_text(encoding="utf-8"))["runs"]
PINNED = {
    "D": "run:fede2ad2fa5d90f7:2",
    "E": "run:94f9624a118995e5",
    "F": "run:14aa6477a666ff65",
    "G": "run:dbaab5578fbff8f3",
}


@pytest.mark.parametrize("case", sorted(PINNED))
def test_d_to_g_stored_run_ids_are_unchanged(case: str) -> None:
    stored = RUNS[case]
    assert stored["run_id"] == PINNED[case]
    base = ids.run_id(stored["inputs"], [], spend_cap_usd=stored["spend_cap_usd"])
    assert PINNED[case].split(":")[:2] == base.split(":")[:2]
    # their stored caps hold lopa_top_n, hashed when they started; it stays in their hash
    assert "lopa_top_n" in stored["inputs"]["caps"]
