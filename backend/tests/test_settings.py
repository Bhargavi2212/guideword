"""The one settings object (spec 0.1)."""

from pathlib import Path

import pytest

from guideword.settings import Settings

KEY = "nb-test-key-value-1234567890"
TAVILY = "tv-test-key-value-0987654321"
SECRET = "advance-secret-value-555"


def _settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("NEBIUS_API_KEY", KEY)
    monkeypatch.setenv("TAVILY_API_KEY", TAVILY)
    monkeypatch.setenv("INTERNAL_ADVANCE_SECRET", SECRET)
    return Settings(_env_file=None)


def test_repr_hides_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch)
    for text in (repr(s), str(s), s.model_dump_json()):
        for value in (KEY, TAVILY, SECRET):
            assert value not in text


def test_keys_readable_on_purpose(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch)
    assert s.nebius_api_key.get_secret_value() == KEY


def test_reads_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("GLOBAL_BUDGET_USD", "GUIDEWORD_ENV", "GUIDEWORD_MOCK"):
        monkeypatch.delenv(name, raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "GLOBAL_BUDGET_USD=25.00\nGUIDEWORD_ENV=hosted\nGUIDEWORD_MOCK=1\n", encoding="utf-8"
    )
    s = Settings(_env_file=env)
    assert s.global_budget_usd == 25.0
    assert s.guideword_env == "hosted"
    assert s.guideword_mock is True


def test_environment_must_be_laptop_or_hosted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GUIDEWORD_ENV", "cloud")
    with pytest.raises(ValueError):
        Settings(_env_file=None)


def test_no_run_cap_setting() -> None:
    # The per-run spend cap lives only in config/caps.yaml (spec 0.1).
    assert not any("cap" in name for name in Settings.model_fields)


def test_expected_fields() -> None:
    assert set(Settings.model_fields) == {
        "nebius_api_key",
        "nebius_base_url",
        "tavily_api_key",
        "global_budget_usd",
        "database_url",
        "guideword_mock",
        "guideword_env",
        "internal_advance_secret",
    }
