"""The one settings object. Keys are read here and nowhere else.

The per-run spend cap and every allowance live only in config/caps.yaml.
"""

from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    # the deployed site (deploy plan D2): the recorded run's committed export, read into an
    # in-memory store; the run `GET /demo` serves; the line its landing marks "start here".
    # None of them has a default: unset, the API reads `database_url` and `/demo` is 501.
    guideword_recorded_dir: str | None = None
    guideword_demo_run_id: str | None = None
    guideword_demo_target_id: str | None = None
