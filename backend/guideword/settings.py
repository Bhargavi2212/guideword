"""The one settings object. Keys are read here and nowhere else.

The per-run spend cap and every allowance live only in config/caps.yaml.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class DemoRunSetting(BaseModel):
    """One run the deployed site offers (review plan R0): its banner, written by Bhargavi, may
    name the start line as `{start_rank}`, filled from the served shortlist."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    banner: str | None = None
    start_target_id: str | None = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    nebius_api_key: SecretStr = SecretStr("")
    nebius_base_url: str = "https://api.tokenfactory.nebius.com/v1"
    tavily_api_key: SecretStr = SecretStr("")
    global_budget_usd: float = 25.0
    database_url: str = "sqlite:///./guideword.db"
    guideword_mock: bool = False
    guideword_env: Literal["laptop", "hosted"] = "laptop"
    internal_advance_secret: SecretStr = SecretStr("")
    # the deployed site (deploy plan D2; several runs, review plan R0): the recorded runs'
    # committed exports, read into one in-memory store; the runs `GET /demo` offers, in the
    # picker's order (the first is the default), each with its banner and start line. Neither
    # has a default: unset, the API reads `database_url` and `/demo` is 501.
    guideword_recorded_dirs: list[str] | None = None
    guideword_demo_runs: list[DemoRunSetting] | None = None
