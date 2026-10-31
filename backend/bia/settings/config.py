from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Environment(StrEnum):
    """The deployment environments the platform can run in.

    Exists so environment-dependent behavior compares against a closed set; read from
    the `ENVIRONMENT` variable by `Settings`.
    """

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    """The logging levels operators can select for the application.

    Exists to reject misspelled levels at startup; read from the `LOG_LEVEL` variable by
    `Settings` and consumed by the logging setup in `bia/api/main.py`.
    """

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class SettingsError(RuntimeError):
    """Signals that the environment does not provide a valid configuration.

    Exists to replace pydantic's validation error, whose text echoes the rejected values
    and could leak secrets into logs. Raised by `load_settings` at application startup.
    """


class Settings(BaseSettings):
    """Holds the environment-driven configuration of the platform.

    Exists as the single place where environment variables are read and validated.
    Consumed through `get_settings` by any vertical that needs configuration.
    """

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    openai_api_key: SecretStr = Field(min_length=1)
    database_url: SecretStr = Field(min_length=1)
    environment: Environment
    log_level: LogLevel = LogLevel.INFO


def _describe_validation_error(error: ValidationError) -> str:
    """Builds a readable summary of the invalid settings, without their values.

    Exists so startup failures name what to fix without exposing secrets; used by
    `load_settings`.

    Args:
        error: The validation error raised while reading the environment.

    Returns:
        str: One `VARIABLE: reason` entry per invalid setting, separated by semicolons.
    """
    return "; ".join(
        f"{str(detail['loc'][0]).upper()}: {detail['msg']}" for detail in error.errors()
    )


def load_settings() -> Settings:
    """Reads and validates the settings from the environment and the `.env` file.

    Exists to fail fast with an actionable message when the configuration is incomplete;
    used by `get_settings` and directly by tests that control the environment.

    Returns:
        Settings: the validated configuration.

    Raises:
        SettingsError: If a variable is missing or invalid.
    """
    try:
        return Settings()
    except ValidationError as error:
        summary = _describe_validation_error(error)
        raise SettingsError(f"Invalid environment configuration: {summary}") from None


@lru_cache
def get_settings() -> Settings:
    """Retrieves the process-wide settings, loading them on first use.

    Exists so the environment is validated once and every consumer shares the same
    configuration; used by the application entrypoint and the verticals.

    Returns:
        Settings: the cached configuration.
    """
    return load_settings()
