"""Loaders for config/models.yaml, routing.yaml and caps.yaml (spec 0.2, Phase 2 plan R18, R19).

Every cap and allowance lives in caps.yaml; the global budget comes from settings. The
loaders refuse an unknown tier, a negative price, a job on a missing tier, a fallback
cycle, allowances that do not add up, max tokens for an unknown job, concurrency that
misses a tier, a retry wait list of the wrong length, a severity reserve at or above the
run cap, and a prompt version with no file.
"""

from collections import Counter
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from guideword.schema.enums import BudgetUse, Environment, Tier

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
DEFAULT_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"

NonNegative = Annotated[float, Field(ge=0)]
Positive = Annotated[float, Field(gt=0)]
PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]


class ConfigError(ValueError):
    def __init__(self, file: str, message: str) -> None:
        super().__init__(f"{file}: {message}")
        self.file = file


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TierRequest(_Strict):
    """How the gateway calls this tier (smoke-test decisions; R34 for tools_with_schema)."""

    structured_output: Literal["json_schema"]
    reasoning: bool
    tool_calling: Literal["native"]
    # tools and the answer schema in one request; false means a tool call, then the answer
    tools_with_schema: bool


class TierModel(_Strict):
    expected_id: str
    input_usd_per_1m: NonNegative
    output_usd_per_1m: NonNegative
    request: TierRequest


class ModelsConfig(_Strict):
    prices_as_of: str
    tiers: dict[Tier, TierModel]


class RoutingConfig(_Strict):
    jobs: dict[str, Tier]
    # prompt name -> version; each names prompts/<name>/<version>.md
    prompts: dict[str, str]
    fallback_order: list[Tier]

    def fallback_after(self, tier: Tier) -> Tier | None:
        """The next tier up when `tier` leaves the catalog, or None at the top."""
        position = self.fallback_order.index(tier)
        return (
            self.fallback_order[position + 1] if position + 1 < len(self.fallback_order) else None
        )


class OrchestratorView(_Strict):
    id_list_max: PositiveInt
    recent_steps: PositiveInt
    dispatch_max_question_ids: PositiveInt


class RunCaps(_Strict):
    run_spend_cap_usd: Positive
    orchestrator_max_steps: PositiveInt
    specialist_max_tool_steps: PositiveInt
    lopa_top_n: PositiveInt
    evidence_top_n: PositiveInt
    question_max_attempts: PositiveInt
    connector_max_input_tokens: PositiveInt
    max_tokens: dict[str, PositiveInt]
    specialist_batch_size: dict[Tier, PositiveInt]
    ai_questions_per_batch: NonNegativeInt
    ai_questions_per_run: NonNegativeInt
    unsure_reanswers_per_run: NonNegativeInt
    orchestrator_view: OrchestratorView
    severity_batch_size: PositiveInt
    severity_output_tokens_estimate: PositiveInt
    plant_screen_max_hypotheses: PositiveInt
    plant_screen_min_valid: NonNegativeInt
    specialist_max_input_tokens: PositiveInt
    # Phase 3 (plan PR 2): the connector's chain limit and the post-analysis batch sizes
    connector_max_chains: PositiveInt
    lopa_batch_size: PositiveInt
    recommendation_batch_size: PositiveInt


class RankingCaps(_Strict):
    outside_library_default_frequency_per_year: Positive
    # P3-4: the piping-leak size above which the large-leak event applies
    pipe_leak_large_above_mm: Positive


class GatewayCaps(_Strict):
    max_attempts: PositiveInt
    # the wait before each retry, so one fewer than max_attempts
    backoff_seconds: list[NonNegative]


class PlantCaps(_Strict):
    section_suggest_cap_usd: Positive


class UseAllowance(_Strict):
    environment: Environment
    allowance_usd: NonNegative


class EnvironmentAllowance(_Strict):
    allowance_usd: NonNegative


class CapsConfig(_Strict):
    run: RunCaps
    plant: PlantCaps
    uses: dict[BudgetUse, UseAllowance]
    environments: dict[Environment, EnvironmentAllowance]
    phase_caps_usd: dict[str, Positive]
    ranking: RankingCaps
    concurrency: dict[Tier, PositiveInt]
    gateway: GatewayCaps

    def run_input_caps(self) -> dict[str, Any]:
        """The caps hashed into a run ID (R18): everything that can change an answer."""
        return {**self.run.model_dump(mode="json"), "ranking": self.ranking.model_dump(mode="json")}

    def environment_allowance(self, environment: Environment) -> float:
        return self.environments[environment].allowance_usd

    def environment_of(self, use: BudgetUse) -> Environment:
        return self.uses[use].environment


class Config(_Strict):
    models: ModelsConfig
    routing: RoutingConfig
    caps: CapsConfig


def _cents(value: float) -> int:
    return round(value * 100)


def _read(directory: Path, name: str) -> Any:
    path = directory / name
    if not path.is_file():
        raise ConfigError(name, "file is missing")
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ConfigError(name, f"not valid YAML: {error}") from error


def _parse[M: BaseModel](name: str, model: type[M], data: Any) -> M:
    try:
        return model.model_validate(data)
    except ValidationError as error:
        raise ConfigError(name, str(error)) from error


def _check_routing(routing: RoutingConfig, models: ModelsConfig) -> None:
    for job, tier in routing.jobs.items():
        if tier not in models.tiers:
            raise ConfigError("routing.yaml", f"job {job} uses tier {tier}, not in models.yaml")
    repeated = [t for t, n in Counter(routing.fallback_order).items() if n > 1]
    if repeated:
        raise ConfigError("routing.yaml", f"fallback cycle: {repeated} appear more than once")
    unknown = set(routing.fallback_order) - set(models.tiers)
    if unknown:
        raise ConfigError("routing.yaml", f"fallback names tiers not in models.yaml: {unknown}")


def _check_prompts(routing: RoutingConfig, prompts_dir: Path) -> None:
    for name, version in routing.prompts.items():
        if not (prompts_dir / name / f"{version}.md").is_file():
            raise ConfigError("routing.yaml", f"prompt {name} {version} has no file in prompts/")


def _check_run_caps(caps: CapsConfig, routing: RoutingConfig, models: ModelsConfig) -> None:
    run = caps.run
    unknown_jobs = set(run.max_tokens) - set(routing.jobs)
    if unknown_jobs:
        raise ConfigError(
            "caps.yaml", f"max_tokens names jobs not in routing.yaml: {sorted(unknown_jobs)}"
        )
    unknown_tiers = set(run.specialist_batch_size) - set(models.tiers)
    if unknown_tiers:
        raise ConfigError(
            "caps.yaml", f"specialist_batch_size names unknown tiers: {unknown_tiers}"
        )
    if set(caps.concurrency) != set(models.tiers):
        raise ConfigError("caps.yaml", "concurrency needs a limit for every tier")
    if len(caps.gateway.backoff_seconds) != caps.gateway.max_attempts - 1:
        raise ConfigError("caps.yaml", "gateway.backoff_seconds needs one wait per retry")
    ceiling = run.max_tokens.get("severity_reason")
    if ceiling is not None and run.severity_output_tokens_estimate > ceiling:
        raise ConfigError(
            "caps.yaml",
            "severity_output_tokens_estimate must not exceed max_tokens.severity_reason",
        )


def _check_caps(caps: CapsConfig, global_budget_usd: float) -> None:
    budget = _cents(global_budget_usd)
    missing_uses = set(BudgetUse) - set(caps.uses)
    if missing_uses:
        raise ConfigError("caps.yaml", f"no allowance for uses {sorted(missing_uses)}")
    if set(caps.environments) != set(Environment):
        raise ConfigError("caps.yaml", "every environment needs an allowance")
    if sum(_cents(u.allowance_usd) for u in caps.uses.values()) != budget:
        raise ConfigError("caps.yaml", "use allowances do not sum to GLOBAL_BUDGET_USD")
    if sum(_cents(e.allowance_usd) for e in caps.environments.values()) != budget:
        raise ConfigError("caps.yaml", "environment allowances do not sum to GLOBAL_BUDGET_USD")
    for environment, allowance in caps.environments.items():
        in_env = sum(
            _cents(u.allowance_usd) for u in caps.uses.values() if u.environment == environment
        )
        if in_env != _cents(allowance.allowance_usd):
            raise ConfigError("caps.yaml", f"uses in {environment} do not sum to its allowance")


def load_config(
    directory: Path | None = None,
    *,
    global_budget_usd: float,
    prompts_dir: Path | None = None,
) -> Config:
    """Load and check config/; `global_budget_usd` comes from settings."""
    root = directory if directory is not None else DEFAULT_CONFIG_DIR
    models = _parse("models.yaml", ModelsConfig, _read(root, "models.yaml"))
    routing = _parse("routing.yaml", RoutingConfig, _read(root, "routing.yaml"))
    caps = _parse("caps.yaml", CapsConfig, _read(root, "caps.yaml"))
    _check_routing(routing, models)
    _check_prompts(routing, prompts_dir if prompts_dir is not None else DEFAULT_PROMPTS_DIR)
    _check_caps(caps, global_budget_usd)
    _check_run_caps(caps, routing, models)
    return Config(models=models, routing=routing, caps=caps)
