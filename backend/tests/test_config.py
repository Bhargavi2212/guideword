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
    assert shipped.caps.phase_caps_usd == {"0": 0.65}


def test_budget_split(shipped: Config) -> None:
    uses = shipped.caps.uses
    assert set(uses) == set(BudgetUse)
    assert {u: uses[u].allowance_usd for u in uses} == {
        BudgetUse.DEVELOPMENT: 5.0,
        BudgetUse.TEST_5: 4.0,
        BudgetUse.BENCHMARK: 8.0,
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
        r"benchmark: \{environment: laptop, allowance_usd: 8\.00\}",
        "benchmark: {environment: laptop, allowance_usd: 9.00}",
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


def test_missing_file(config_dir: Path) -> None:
    (config_dir / "routing.yaml").unlink()
    _refused(config_dir, "routing.yaml")


def test_no_caps_in_code() -> None:
    """Budgets and caps are never literals in the loader (CLAUDE.md section 4)."""
    source = (Path(__file__).resolve().parents[1] / "guideword" / "config.py").read_text(
        encoding="utf-8"
    )
    for literal in ("19", "25", "0.65", "0.05", "80000"):
        assert re.search(rf"(?<![\w.]){re.escape(literal)}(?![\w.])", source) is None, literal
