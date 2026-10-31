import logging

from fastapi import FastAPI

from bia.api.artifacts import HealthResponse, HealthStatus
from bia.settings.config import LogLevel, get_settings

logger = logging.getLogger(__name__)


def _configure_logging(log_level: LogLevel) -> None:
    """Configures the root logger for the whole application.

    Exists because the entrypoint is the only place allowed to set up log handlers; used
    by `create_app`.

    Args:
        log_level: The minimum level of the records to emit.

    Returns:
        None: the logging module is configured in place.
    """
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _health() -> HealthResponse:
    """Reports that the service is up and able to answer requests.

    Exists so deploys and uptime checks can verify the service without touching its
    dependencies; served as `GET /health`.

    Returns:
        HealthResponse: the current status of the service.
    """
    return HealthResponse(status=HealthStatus.OK)


def create_app() -> FastAPI:
    """Builds the FastAPI application, validating the configuration first.

    Exists so a deploy with an incomplete environment fails at startup instead of on the
    first request; used to create the module-level `app` served by uvicorn and Vercel.

    Returns:
        FastAPI: the application with its routes registered.
    """
    settings = get_settings()
    _configure_logging(settings.log_level)
    application = FastAPI(title="Bia Agent Platform")
    application.add_api_route("/health", _health, methods=["GET"], response_model=HealthResponse)
    logger.info("Application started in %s environment", settings.environment.value)
    return application


app = create_app()
