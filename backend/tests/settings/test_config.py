from pathlib import Path

import pytest

from bia.settings.config import Environment, LogLevel, Settings, SettingsError, load_settings


@pytest.fixture(autouse=True)
def _isolate_from_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Points settings at a nonexistent `.env` so a developer's real file cannot interfere.

    Args:
        tmp_path: Temporary directory that does not contain a `.env` file.
        monkeypatch: Pytest helper that restores the configuration after the test.
    """
    config = {**Settings.model_config, "env_file": tmp_path / ".env"}
    monkeypatch.setattr(Settings, "model_config", config)


def test_load_settings_reads_values_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies the variables reach their typed fields."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("OPENAI_API_KEY", "real-key")

    settings = load_settings()

    assert settings.environment is Environment.PRODUCTION
    assert settings.log_level is LogLevel.DEBUG
    assert settings.openai_api_key.get_secret_value() == "real-key"


def test_log_level_defaults_to_info(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies the only optional variable falls back to INFO."""
    monkeypatch.delenv("LOG_LEVEL")

    assert load_settings().log_level is LogLevel.INFO


def test_cors_origins_default_to_the_local_frontend(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies local development works, and no other site is trusted, without configuring it."""
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)

    assert load_settings().cors_allowed_origins == ["http://localhost:3000"]


def test_cors_origins_are_read_as_a_json_list(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies a deploy can name its frontend through the environment."""
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", '["https://bia.example"]')

    assert load_settings().cors_allowed_origins == ["https://bia.example"]


@pytest.mark.parametrize(
    "variable", ["OPENAI_API_KEY", "DATABASE_URL", "API_ACCESS_PASSWORD", "ENVIRONMENT"]
)
def test_missing_variable_fails_naming_it(variable: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies each required variable, when absent, is named in the startup error."""
    monkeypatch.delenv(variable)

    with pytest.raises(SettingsError, match=variable):
        load_settings()


def test_empty_secret_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies a blank value copied from `.env.example` does not pass as configured."""
    monkeypatch.setenv("OPENAI_API_KEY", "")

    with pytest.raises(SettingsError, match="OPENAI_API_KEY"):
        load_settings()


def test_short_access_password_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies a guessable password cannot protect a public deployment."""
    monkeypatch.setenv("API_ACCESS_PASSWORD", "too-short")

    with pytest.raises(SettingsError, match="API_ACCESS_PASSWORD"):
        load_settings()


def test_error_does_not_expose_rejected_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies the startup error never carries configured values into logs."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:s3cret@host/db")
    monkeypatch.setenv("ENVIRONMENT", "s3cret-environment")

    with pytest.raises(SettingsError) as error_info:
        load_settings()

    assert "ENVIRONMENT" in str(error_info.value)
    assert "s3cret" not in str(error_info.value)
    assert error_info.value.__cause__ is None
    assert error_info.value.__suppress_context__ is True
