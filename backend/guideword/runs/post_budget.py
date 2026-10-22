"""The post-analysis budget and settings (spec 3.6; plan PR 5, P3-2, Q19, G8).

The four post-analysis steps (chains, chain severity, LOPA, recommendations) check their
calls against the run's own `post_spend_cap_usd`, not the analysis cap: `post_spent` is the
sum of `cap_cost_usd` over the run's model calls whose job is a post-analysis job, so there is
no new counter. The analysis and its severity reserve read the analysis cap as before.

Settings: a value the stored caps hold is read from them (G8: `lopa_top_n` of an extended
run is its own); a value they lack, such as `connector_max_chains` on a run from before
Phase 3, is read from the current config (spec 3.6). Extension records which source each
value came from.
"""

from collections.abc import Sequence
from typing import Any

from guideword.config import Config
from guideword.gateway.client import RunBudget
from guideword.runs.store import StepWriter
from guideword.schema.records import ModelCall, Run

# Phase 4 adds the evidence step and its precedent judge (plan PR 5b)
POST_JOBS = frozenset(
    {"connector", "chain_severity", "lopa_argument", "recommendation", "precedent_judge"}
)
POST_STEPS = ("chains", "chain_severity", "lopa", "recommendations", "evidence")
# the prompts the post-analysis steps load (recorded on extension)
POST_PROMPTS = (
    "connector",
    "lopa_argument",
    "recommendation",
    "severity_chain",
    "precedent_judge",
)
POST_SETTINGS = (
    "lopa_top_n",
    "connector_max_input_tokens",
    "connector_max_chains",
    "lopa_batch_size",
    "recommendation_batch_size",
    "chain_severity_batch_size",
)
# connector/v2 plan, Q5: post-step caps a new run does not hash into its ID; recorded on its
# run_extended event with the post-step prompt versions (POST_PROMPTS) instead
POST_HASH_FREE_CAPS = (
    "connector_max_chains",
    "lopa_batch_size",
    "recommendation_batch_size",
    "lopa_top_n",
    "chain_severity_batch_size",
)
FROM_RUN = "run.caps"
FROM_CONFIG = "config"


def post_spent(calls: Sequence[ModelCall]) -> float:
    """Q19: what the post-analysis jobs have counted against the post cap."""
    return sum(c.cap_cost_usd for c in calls if c.job in POST_JOBS)


def post_budget(writer: StepWriter) -> RunBudget:
    """The budget a post-analysis call is checked against: `post_spent + estimate <=
    post_spend_cap_usd`."""
    run = writer.run
    return RunBudget(run.id, post_spent(writer.model_calls()), run.post_spend_cap_usd)


def post_setting(run: Run, config: Config, key: str) -> int:
    stored = run.caps.get(key)
    return int(stored) if stored is not None else int(getattr(config.caps.run, key))


# Phase 4 (P4-9): the evidence step's settings, read like the post settings (plan G4)
EVIDENCE_SETTINGS = (
    "evidence_top_n",
    "precedent_candidates",
    "tavily_searches_per_run",
    "tavily_max_results",
    "overflow_confirm_minutes",
    "heat_up_confirm_minutes",
)


def evidence_setting(run: Run, config: Config, key: str) -> Any:
    """A value the run's stored caps hold (D–G and the Phase 3 demo run hold
    `evidence_top_n`), else the current `evidence:` block."""
    stored = run.caps.get(key)
    return stored if stored is not None else getattr(config.caps.evidence, key)


def evidence_settings(run: Run, config: Config) -> dict[str, dict[str, Any]]:
    return {
        key: {
            "value": evidence_setting(run, config, key),
            "source": FROM_RUN if run.caps.get(key) is not None else FROM_CONFIG,
        }
        for key in EVIDENCE_SETTINGS
    }


def post_settings(run: Run, config: Config) -> dict[str, dict[str, Any]]:
    """Every post-analysis setting with the value used and where it came from."""
    return {
        key: {
            "value": post_setting(run, config, key),
            "source": FROM_RUN if run.caps.get(key) is not None else FROM_CONFIG,
        }
        for key in POST_SETTINGS
    }
