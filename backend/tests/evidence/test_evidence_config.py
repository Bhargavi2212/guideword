"""The evidence step's settings, routing and hashing (Phase 4 spec 4.4, P4-9; plan PR 5b, Q3).

The `evidence:` caps block, the `precedent_judge` job and its `max_tokens`, and every other
post-step job and its `max_tokens` leave a new run's hashed inputs: changing any of them never
moves a run ID. Stored runs keep their IDs (test_dev_run_ids.py)."""

from typing import Any

import pytest

from guideword.config import Config, load_config
from guideword.runs.case import run_settings
from guideword.runs.post_budget import POST_JOBS, POST_PROMPTS, POST_STEPS
from guideword.runs.start import AFTER_ANALYSIS
from guideword.schema.enums import Tier

EVIDENCE_KEYS = (
    "evidence_top_n",
    "precedent_candidates",
    "tavily_searches_per_run",
    "tavily_max_results",
    "overflow_confirm_minutes",
    "heat_up_confirm_minutes",
    "te_hours",
)


@pytest.fixture(scope="module")
def config() -> Config:
    return load_config(global_budget_usd=25.0)


def _with_evidence(config: Config, **changes: Any) -> Config:
    evidence = config.caps.evidence.model_copy(update=changes)
    return config.model_copy(update={"caps": config.caps.model_copy(update={"evidence": evidence})})


def _with_max_tokens(config: Config, job: str, value: int) -> Config:
    tokens = {**config.caps.run.max_tokens, job: value}
    run = config.caps.run.model_copy(update={"max_tokens": tokens})
    return config.model_copy(update={"caps": config.caps.model_copy(update={"run": run})})


def _with_job(config: Config, job: str, tier: Tier) -> Config:
    routing = config.routing.model_copy(update={"jobs": {**config.routing.jobs, job: tier}})
    return config.model_copy(update={"routing": routing})


def test_the_evidence_block_holds_the_spec_values(config: Config) -> None:
    evidence = config.caps.evidence
    assert {key: getattr(evidence, key) for key in EVIDENCE_KEYS} == {
        "evidence_top_n": 5,
        "precedent_candidates": 5,
        "tavily_searches_per_run": 5,
        "tavily_max_results": 5,
        "overflow_confirm_minutes": 60,
        "heat_up_confirm_minutes": 60,
        "te_hours": 4,
    }
    assert not hasattr(config.caps.run, "evidence_top_n")


def test_the_precedent_judge_is_routed_to_super_with_its_prompt(config: Config) -> None:
    assert config.routing.jobs["precedent_judge"] == Tier.SUPER
    assert config.routing.prompts["precedent_judge"] == "v1"
    assert config.caps.run.max_tokens["precedent_judge"] > 0


def test_evidence_joins_the_post_step_sets(config: Config) -> None:
    assert "precedent_judge" in POST_JOBS
    assert "precedent_judge" in POST_PROMPTS
    assert POST_STEPS[-1] == "evidence"
    assert "evidence" in AFTER_ANALYSIS


def test_a_new_run_stores_no_post_job_routing_or_max_tokens(config: Config) -> None:
    """Q3: the post-step jobs and their max_tokens are recorded on run_extended instead."""
    settings = run_settings(config)
    assert not set(POST_JOBS) & set(settings.routing_config)
    assert not set(POST_JOBS) & set(settings.caps["max_tokens"])
    assert "evidence_top_n" not in settings.caps
    assert "evidence" not in settings.caps
    # the analysis jobs are still hashed
    assert settings.routing_config["orchestrator"] == "ultra"
    assert settings.caps["max_tokens"]["specialist_bulk"] == 12288


@pytest.mark.parametrize("key", EVIDENCE_KEYS)
def test_evidence_settings_leave_new_run_ids_unchanged(config: Config, key: str) -> None:
    changed = _with_evidence(config, **{key: getattr(config.caps.evidence, key) + 1})
    assert run_settings(changed) == run_settings(config)


@pytest.mark.parametrize("job", sorted(POST_JOBS))
def test_post_jobs_and_their_max_tokens_leave_new_run_ids_unchanged(
    config: Config, job: str
) -> None:
    assert run_settings(_with_max_tokens(config, job, 999)) == run_settings(config)
    assert run_settings(_with_job(config, job, Tier.LIGHTNING)) == run_settings(config)


def test_an_analysis_job_still_moves_the_run_id(config: Config) -> None:
    assert run_settings(_with_max_tokens(config, "orchestrator", 999)) != run_settings(config)
