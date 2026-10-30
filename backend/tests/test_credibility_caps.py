"""The `credibility` caps block (Phase 9 spec 9.3; plan): the settings of the holistic passes
and the comparative ranking, hashed into a run's caps like the run and ranking blocks, with the
shipped values the plan names; a run stored without it reads as one pass."""

import pytest

from guideword.config import Config, CredibilityCaps, load_config


@pytest.fixture(scope="module")
def shipped() -> Config:
    return load_config(global_budget_usd=25.0)


def test_the_shipped_block_holds_the_plans_values(shipped: Config) -> None:
    block = shipped.caps.credibility
    assert isinstance(block, CredibilityCaps)
    assert block.holistic_passes == 3
    assert block.rank_orders == 3
    assert block.ranker == "listwise"
    assert block.rrf_k == 60
    assert block.pairwise_top_k == 6
    assert block.sweep_candidates == 10
    assert block.verify_top_n == 10
    assert block.prior_weight == 1.0
    assert block.conformal_min_cases == 50


def test_the_block_is_hashed_into_a_runs_caps(shipped: Config) -> None:
    caps = shipped.caps.run_input_caps()
    assert caps["credibility"] == shipped.caps.credibility.model_dump(mode="json")
    assert caps["credibility"]["holistic_passes"] == 3


def test_the_ranker_is_listwise_or_setwise() -> None:
    with pytest.raises(ValueError):
        CredibilityCaps(
            holistic_passes=3,
            rank_orders=3,
            ranker="random",  # type: ignore[arg-type]
            rrf_k=60,
            pairwise_top_k=6,
            sweep_candidates=10,
            verify_top_n=10,
            prior_weight=1.0,
            conformal_min_cases=50,
        )


def test_every_count_is_positive_and_the_weight_non_negative() -> None:
    good = dict(
        holistic_passes=1,
        rank_orders=1,
        ranker="setwise",
        rrf_k=1,
        pairwise_top_k=2,
        sweep_candidates=0,
        verify_top_n=0,
        prior_weight=0.0,
        conformal_min_cases=1,
    )
    CredibilityCaps(**good)  # type: ignore[arg-type]
    for key, bad in (
        ("holistic_passes", 0),
        ("rank_orders", 0),
        ("rrf_k", 0),
        ("prior_weight", -1.0),
    ):
        with pytest.raises(ValueError):
            CredibilityCaps(**{**good, key: bad})  # type: ignore[arg-type]
