import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from bia.api import agents as agents_api
from bia.api import builder as builder_api
from bia.api import rag as rag_api
from bia.api import runtime as runtime_api
from bia.api import tracing as tracing_api
from bia.api.artifacts import HealthResponse, HealthStatus
from bia.api.auth import BasicAuthMiddleware, PublicPath
from bia.api.catalog import models as catalog_models
from bia.api.catalog import tools as catalog_tools
from bia.builder.system_agents import sync_system_agents
from bia.catalog.tools.sync import sync_tools
from bia.database.connection import database_session, get_engine
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


@asynccontextmanager
async def _lifespan(_application: FastAPI) -> AsyncIterator[None]:
    """Syncs the tool catalog and the system agents before the application serves requests.

    Exists so the database reflects the code of the running deploy. A failure aborts the
    startup instead of serving a catalog or a builder that may not match the code. Registered
    on the application by `create_app`.

    Args:
        _application: The application starting up; required by FastAPI's signature.

    Returns:
        AsyncIterator[None]: yields while the application runs.
    """
    with database_session(get_engine()) as session:
        sync_tools(session)
        sync_system_agents(session)
    yield


def create_app() -> FastAPI:
    """Builds the FastAPI application, validating the configuration first.

    Exists so a deploy with an incomplete environment fails at startup instead of on the
    first request; used to create the module-level `app` served by uvicorn and Vercel.

    Returns:
        FastAPI: the application with its routes registered.
    """
    settings = get_settings()
    _configure_logging(settings.log_level)
    application = FastAPI(title="Bia Agent Platform", lifespan=_lifespan)
    application.add_middleware(
        BasicAuthMiddleware, password=settings.api_access_password.get_secret_value()
    )
    application.add_api_route(
        PublicPath.HEALTH, _health, methods=["GET"], response_model=HealthResponse
    )
    application.include_router(catalog_models.router)
    application.include_router(catalog_tools.router)
    application.include_router(agents_api.router)
    application.include_router(tracing_api.router)
    application.include_router(runtime_api.router)
    application.include_router(rag_api.router)
    application.include_router(builder_api.router)
    logger.info("Application started in %s environment", settings.environment.value)
    return application


app = create_app()
