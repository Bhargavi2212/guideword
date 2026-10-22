"""Config loaders (spec 0.2): the shipped files load; each inconsistency is refused."""

import re
import shutil
from pathlib import Path

import pytest

from guideword.config import Config, ConfigError, load_config
from guideword.schema.enums import BudgetUse, Environment, Tier

CONFIG = Path(__file__).resolve().parents[2] / "config"
BUDGET = 25.0


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    target = tmp_path / "config"
    shutil.copytree(CONFIG, target)
    return target


def _edit(directory: Path, name: str, pattern: str, replacement: str) -> None:
    path = directory / name
    text = path.read_text(encoding="utf-8")
    new, n = re.subn(pattern, replacement, text, count=1, flags=re.M)
    assert n, f"test pattern did not match: {pattern}"
    path.write_text(new, encoding="utf-8", newline="\n")


def _refused(directory: Path, name: str, budget: float = BUDGET) -> None:
    with pytest.raises(ConfigError, match=re.escape(name)):
        load_config(directory, global_budget_usd=budget)


# --- the shipped config ---------------------------------------------------------------------


@pytest.fixture(scope="module")
def shipped() -> Config:
    return load_config(CONFIG, global_budget_usd=BUDGET)


def test_models(shipped: Config) -> None:
    assert set(shipped.models.tiers) == set(Tier)
    ultra = shipped.models.tiers[Tier.ULTRA]
    assert ultra.expected_id == "nvidia/Nemotron-3-Ultra-550b-a55b"
    assert (ultra.input_usd_per_1m, ultra.output_usd_per_1m) == (1.00, 3.00)
    lightning = shipped.models.tiers[Tier.LIGHTNING]
    assert (lightning.input_usd_per_1m, lightning.output_usd_per_1m) == (0.06, 0.24)


def test_routing(shipped: Config) -> None:
    jobs = shipped.routing.jobs
    assert jobs["orchestrator"] == Tier.ULTRA
    assert jobs["section_suggestion"] == Tier.SUPER
    assert jobs["specialist_bulk"] == Tier.LIGHTNING
    assert jobs["extraction"] == Tier.LIGHTNING
    assert Tier.NANO not in jobs.values()
    assert shipped.routing.fallback_order == [Tier.NANO, Tier.LIGHTNING, Tier.SUPER, Tier.ULTRA]


def test_caps(shipped: Config) -> None:
    run = shipped.caps.run
    assert run.run_spend_cap_usd == 1.00
    assert run.orchestrator_max_steps == 60
    assert run.specialist_max_tool_steps == 2
    assert (run.lopa_top_n, run.evidence_top_n) == (10, 5)
    assert run.question_max_attempts == 2
    assert run.connector_max_input_tokens == 80000
    assert shipped.caps.plant.section_suggest_cap_usd == 0.05
    # Phase 2 adds its cap (specs/phase-2.md)
    assert shipped.caps.phase_caps_usd == {"0": 0.65, "2": 8.50, "3": 2.50}


def test_phase_2_run_caps(shipped: Config) -> None:
    """Decisions R18 and R38, with the values raised after the case D dev run (the severity
    reserve is computed by code, so it is no longer a setting)."""
    run = shipped.caps.run
    assert run.max_tokens == {
        "orchestrator": 4096,
        "specialist_bulk": 12288,
        "specialist_hard": 12288,
        "unsure_answer": 6144,
        "severity_reason": 12288,
        "section_suggestion": 6144,
        "test5a": 8192,
        "plant_screen": 12288,
        # Phase 3 (plan PR 2): the post-analysis Ultra jobs, start values as severity_reason
        "connector": 12288,
        "lopa_argument": 12288,
        "recommendation": 12288,
        "chain_severity": 12288,
    }
    assert run.specialist_batch_size == {
        Tier.LIGHTNING: 5,
        Tier.NANO: 10,
        Tier.SUPER: 5,
        Tier.ULTRA: 5,
    }
    assert (run.ai_questions_per_batch, run.ai_questions_per_run) == (2, 20)
    assert run.unsure_reanswers_per_run == 10
    assert run.orchestrator_view.model_dump() == {
        "id_list_max": 20,
        "recent_steps": 5,
        "dispatch_max_question_ids": 60,
    }
    assert run.severity_batch_size == 10
    # the severity reserve prices each call at this, under the max_tokens ceiling
    assert run.severity_output_tokens_estimate == 4700
    assert run.plant_screen_max_hypotheses == 12
    assert run.plant_screen_min_valid == 5
    assert run.specialist_max_input_tokens == 24000
    assert shipped.caps.ranking.outside_library_default_frequency_per_year == 0.1


def test_phase_3_run_caps(shipped: Config) -> None:
    """Plan PR 2 (Q9, Q12): in the hashed run block, so they move only new runs' IDs; an
    extended run reads them from the current config (spec 3.6)."""
    run = shipped.caps.run
    assert run.connector_max_chains == 10
    assert run.lopa_batch_size == 5
    assert run.recommendation_batch_size == 5
    caps = shipped.caps.run_input_caps()
    for key in ("connector_max_chains", "lopa_batch_size", "recommendation_batch_size"):
        assert key in caps, key
    for job in ("connector", "lopa_argument", "recommendation", "chain_severity"):
        assert caps["max_tokens"][job] == 12288, job
    assert shipped.routing.jobs["chain_severity"] == Tier.ULTRA


def test_gateway_caps(shipped: Config) -> None:
    caps = shipped.caps
    assert caps.concurrency == {Tier.ULTRA: 3, Tier.SUPER: 3, Tier.LIGHTNING: 5, Tier.NANO: 3}
    assert caps.gateway.max_attempts == 3
    assert caps.gateway.backoff_seconds == [1.0, 2.0]


def test_tier_request_settings(shipped: Config) -> None:
    """From the smoke-test decisions: Ultra and Super reason, Lightning and Nano do not."""
    tiers = shipped.models.tiers
    assert {t: tiers[t].request.reasoning for t in Tier} == {
        Tier.ULTRA: True,
        Tier.SUPER: True,
        Tier.LIGHTNING: False,
        Tier.NANO: False,
    }
    for tier in Tier:
        request = tiers[tier].request
        assert (request.structured_output, request.tool_calling) == ("json_schema", "native")
        # the gateway check of 2026-10-15: tool calls and a strict schema do not combine (R34)
        assert request.tools_with_schema is False


def test_prompt_versions_name_existing_files(shipped: Config) -> None:
    assert shipped.routing.prompts == {
        "orchestrator": "v2",
        "section_suggestion": "v1",
        "severity": "v2",
        "test5a": "v1",
        "plant_screen": "v3",
        # Phase 3 (plan PR 2, Q5)
        "connector": "v2",
        "lopa_argument": "v3",
        "recommendation": "v2",
        "severity_chain": "v2",
        **{
            f"specialists/{a}": "v2"
            for a in ("process", "chemistry", "piping", "procedures", "maintenance", "dust")
        },
    }
    assert shipped.routing.jobs["test5a"] == Tier.ULTRA


def test_run_input_caps_hold_everything_that_changes_answers(shipped: Config) -> None:
    """R18: the run block and ranking enter Run.caps; concurrency, retries, allowances do not."""
    caps = shipped.caps.run_input_caps()
    assert caps["max_tokens"]["specialist_bulk"] == 12288
    assert caps["severity_batch_size"] == 10
    assert "severity_reserve_usd" not in caps
    # R43: it changes what the model sees, so it is hashed into the run ID
    assert caps["specialist_max_input_tokens"] == 24000
    assert caps["ranking"] == {
        "outside_library_default_frequency_per_year": 0.1,
        # P3-4: C20 above this size uses the large-leak event; it changes ratings, so hashed
        "pipe_leak_large_above_mm": 150,
        # lead tie-break plan: it changes which finding leads a confirmed line, so hashed
        "lead_prefers_own_section": True,
    }
    for left_out in ("concurrency", "gateway", "uses", "environments", "phase_caps_usd"):
        assert left_out not in caps


def test_budget_split(shipped: Config) -> None:
    uses = shipped.caps.uses
    assert set(uses) == set(BudgetUse)
    assert {u: uses[u].allowance_usd for u in uses} == {
        BudgetUse.DEVELOPMENT: 5.0,
        BudgetUse.TEST_5: 7.5,
        BudgetUse.BENCHMARK: 4.5,
        BudgetUse.VIDEO: 2.0,
        BudgetUse.DEMO_RECORDING: 1.0,
        BudgetUse.JUDGING: 3.0,
        BudgetUse.BUFFER: 2.0,
    }
    assert shipped.caps.environment_allowance(Environment.LAPTOP) == 19.0
    assert shipped.caps.environment_allowance(Environment.HOSTED) == 6.0
    assert shipped.caps.environment_of(BudgetUse.VIDEO) == Environment.LAPTOP
    assert shipped.caps.environment_of(BudgetUse.JUDGING) == Environment.HOSTED


def test_fallback_after(shipped: Config) -> None:
    assert shipped.routing.fallback_after(Tier.LIGHTNING) == Tier.SUPER
    assert shipped.routing.fallback_after(Tier.ULTRA) is None


# --- refusals (spec 0.2 acceptance) -----------------------------------------------------------


def test_unknown_tier(config_dir: Path) -> None:
    _edit(config_dir, "models.yaml", r"^  nano:", "  giant:")
    _refused(config_dir, "models.yaml")


def test_negative_price(config_dir: Path) -> None:
    _edit(config_dir, "models.yaml", r"input_usd_per_1m: 0\.30", "input_usd_per_1m: -0.30")
    _refused(config_dir, "models.yaml")


def test_job_mapped_to_missing_tier(config_dir: Path) -> None:
    _edit(config_dir, "routing.yaml", r"^  connector: ultra", "  connector: mega")
    _refused(config_dir, "routing.yaml")


def test_job_mapped_to_tier_not_in_models(config_dir: Path) -> None:
    _edit(config_dir, "models.yaml", r"^  nano:\n(    .*\n){3}", "")
    _edit(config_dir, "routing.yaml", r"^  extraction: lightning", "  extraction: nano")
    _refused(config_dir, "routing.yaml")


def test_fallback_cycle(config_dir: Path) -> None:
    _edit(
        config_dir,
        "routing.yaml",
        r"^fallback_order: .*$",
        "fallback_order: [nano, lightning, super, lightning]",
    )
    _refused(config_dir, "routing.yaml")


def test_use_allowances_must_sum_to_global_budget(config_dir: Path) -> None:
    _edit(
        config_dir,
        "caps.yaml",
        r"benchmark: \{environment: laptop, allowance_usd: 4\.50\}",
        "benchmark: {environment: laptop, allowance_usd: 5.50}",
    )
    _edit(
        config_dir,
        "caps.yaml",
        r"laptop: \{allowance_usd: 19\.00\}",
        "laptop: {allowance_usd: 20.00}",
    )
    _refused(config_dir, "caps.yaml")


def test_environment_allowances_must_sum_to_global_budget(config_dir: Path) -> None:
    _edit(
        config_dir,
        "caps.yaml",
        r"hosted: \{allowance_usd: 6\.00\}",
        "hosted: {allowance_usd: 7.00}",
    )
    _refused(config_dir, "caps.yaml")


def test_global_budget_comes_from_settings(config_dir: Path) -> None:
    _refused(config_dir, "caps.yaml", budget=50.0)


def test_use_with_unknown_environment(config_dir: Path) -> None:
    _edit(config_dir, "caps.yaml", r"video: \{environment: laptop,", "video: {environment: cloud,")
    _refused(config_dir, "caps.yaml")


def test_uses_per_environment_must_sum_to_its_allowance(config_dir: Path) -> None:
    # move $2 of video spend to hosted: totals still 25, but laptop uses sum to 17, not 19
    _edit(config_dir, "caps.yaml", r"video: \{environment: laptop,", "video: {environment: hosted,")
    _refused(config_dir, "caps.yaml")


def test_unknown_use(config_dir: Path) -> None:
    _edit(config_dir, "caps.yaml", r"^  buffer:", "  holiday:")
    _refused(config_dir, "caps.yaml")


def test_negative_cap(config_dir: Path) -> None:
    _edit(config_dir, "caps.yaml", r"run_spend_cap_usd: 1\.00", "run_spend_cap_usd: -1.00")
    _refused(config_dir, "caps.yaml")


def test_unknown_cap_key(config_dir: Path) -> None:
    _edit(config_dir, "caps.yaml", r"^  lopa_top_n: 10", "  lopa_top_n: 10\n  surprise: 1")
    _refused(config_dir, "caps.yaml")


def test_max_tokens_for_an_unknown_job(config_dir: Path) -> None:
    _edit(config_dir, "caps.yaml", r"^    test5a: 8192", "    test5a: 8192\n    poetry: 100")
    _refused(config_dir, "caps.yaml")


def test_concurrency_must_cover_every_tier(config_dir: Path) -> None:
    _edit(
        config_dir,
        "caps.yaml",
        r"^concurrency: .*$",
        "concurrency: {ultra: 3, super: 3, lightning: 5}",
    )
    _refused(config_dir, "caps.yaml")


def test_backoff_has_one_wait_per_retry(config_dir: Path) -> None:
    _edit(config_dir, "caps.yaml", r"backoff_seconds: \[1, 2\]", "backoff_seconds: [1]")
    _refused(config_dir, "caps.yaml")


def test_severity_output_estimate_above_its_max_tokens_is_refused(config_dir: Path) -> None:
    _edit(
        config_dir,
        "caps.yaml",
        r"severity_output_tokens_estimate: 4700",
        "severity_output_tokens_estimate: 20000",
    )
    _refused(config_dir, "caps.yaml")


def test_a_fixed_severity_reserve_is_refused(config_dir: Path) -> None:
    """The reserve is computed by code from the findings still to rate (case D dev run)."""
    _edit(
        config_dir,
        "caps.yaml",
        r"^  severity_batch_size: 10",
        "  severity_batch_size: 10\n  severity_reserve_usd: 0.15",
    )
    _refused(config_dir, "caps.yaml")


def test_batch_size_for_an_unknown_tier(config_dir: Path) -> None:
    _edit(config_dir, "caps.yaml", r"^    nano: 10", "    nano: 10\n    mega: 10")
    _refused(config_dir, "caps.yaml")


def test_prompt_version_without_its_file(config_dir: Path) -> None:
    _edit(config_dir, "routing.yaml", r"section_suggestion: v1$", "section_suggestion: v9")
    _refused(config_dir, "routing.yaml")


def test_tier_without_request_settings(config_dir: Path) -> None:
    _edit(
        config_dir,
        "models.yaml",
        r"^    request: \{structured_output: json_schema, reasoning: false, (.*)\n",
        "",
    )
    _refused(config_dir, "models.yaml")


def test_missing_file(config_dir: Path) -> None:
    (config_dir / "routing.yaml").unlink()
    _refused(config_dir, "routing.yaml")


def test_no_caps_in_code() -> None:
    """Budgets and caps are never literals in the loader (CLAUDE.md section 4)."""
    source = (Path(__file__).resolve().parents[1] / "guideword" / "config.py").read_text(
        encoding="utf-8"
    )
    for literal in ("19", "25", "0.65", "0.05", "80000", "0.15", "6144", "0.1", "5.00"):
        assert re.search(rf"(?<![\w.]){re.escape(literal)}(?![\w.])", source) is None, literal
