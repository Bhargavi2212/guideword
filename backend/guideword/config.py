"""Loaders for config/models.yaml, routing.yaml and caps.yaml (spec 0.2).

Every cap and allowance lives in caps.yaml; the global budget comes from settings. The
loaders refuse an unknown tier, a negative price, a job on a missing tier, a fallback
cycle, and allowances that do not add up.
"""

from collections import Counter
from pathlib import Path
from typing import Annotated, Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from guideword.schema.enums import BudgetUse, Environment, Tier

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"

NonNegative = Annotated[float, Field(ge=0)]
Positive = Annotated[float, Field(gt=0)]
PositiveInt = Annotated[int, Field(gt=0)]


class ConfigError(ValueError):
    def __init__(self, file: str, message: str) -> None:
        super().__init__(f"{file}: {message}")
        self.file = file


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TierModel(_Strict):
    expected_id: str
    input_usd_per_1m: NonNegative
    output_usd_per_1m: NonNegative


class ModelsConfig(_Strict):
    prices_as_of: str
    tiers: dict[Tier, TierModel]


class RoutingConfig(_Strict):
    jobs: dict[str, Tier]
    fallback_order: list[Tier]

    def fallback_after(self, tier: Tier) -> Tier | None:
        """The next tier up when `tier` leaves the catalog, or None at the top."""
        position = self.fallback_order.index(tier)
        return (
            self.fallback_order[position + 1] if position + 1 < len(self.fallback_order) else None
        )


class RunCaps(_Strict):
    run_spend_cap_usd: Positive
    orchestrator_max_steps: PositiveInt
    specialist_max_tool_steps: PositiveInt
    lopa_top_n: PositiveInt
    evidence_top_n: PositiveInt
    question_max_attempts: PositiveInt
    connector_max_input_tokens: PositiveInt


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


def load_config(directory: Path | None = None, *, global_budget_usd: float) -> Config:
    """Load and check config/; `global_budget_usd` comes from settings."""
    root = directory if directory is not None else DEFAULT_CONFIG_DIR
    models = _parse("models.yaml", ModelsConfig, _read(root, "models.yaml"))
    routing = _parse("routing.yaml", RoutingConfig, _read(root, "routing.yaml"))
    caps = _parse("caps.yaml", CapsConfig, _read(root, "caps.yaml"))
    _check_routing(routing, models)
    _check_caps(caps, global_budget_usd)
    return Config(models=models, routing=routing, caps=caps)
