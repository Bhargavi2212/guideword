"""Phase 6 statistics (spec P6-11; acceptance 8): the Wilson 95% interval and the exact McNemar
test, against Cowork's hand-worked values in `bench/example_stats.json` (relative 1e-9)."""

import json
import math
from pathlib import Path

import pytest

from guideword.bench.stats import mcnemar_exact, smallest_one_way_discordant, wilson_95

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = json.loads((ROOT / "bench" / "example_stats.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("row", EXAMPLE["wilson_95"], ids=lambda r: f"{r['x']}of{r['n']}")
def test_wilson_matches_example_stats(row: dict[str, float]) -> None:
    low, high = wilson_95(int(row["x"]), int(row["n"]))
    assert math.isclose(low, row["low"], rel_tol=1e-9, abs_tol=1e-12)
    assert math.isclose(high, row["high"], rel_tol=1e-9, abs_tol=1e-12)


@pytest.mark.parametrize("row", EXAMPLE["mcnemar_exact"], ids=lambda r: f"b{r['b']}c{r['c']}")
def test_mcnemar_matches_example_stats(row: dict[str, float]) -> None:
    assert math.isclose(mcnemar_exact(int(row["b"]), int(row["c"])), row["p"], rel_tol=1e-9)


def test_the_power_sentence_comes_from_example_stats() -> None:
    assert (
        smallest_one_way_discordant() == EXAMPLE["smallest_all_one_way_discordant_for_p_below_0_05"]
    )


def test_wilson_refuses_impossible_counts() -> None:
    with pytest.raises(ValueError):
        wilson_95(3, 2)
    with pytest.raises(ValueError):
        wilson_95(0, 0)
