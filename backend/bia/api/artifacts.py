from enum import StrEnum

from pydantic import BaseModel


class HealthStatus(StrEnum):
    """The states the service can report about itself.

    Exists so the health contract is a closed set; produced by `GET /health` in
    `bia/api/main.py` and consumed by deploy checks.
    """

    OK = "ok"


class HealthResponse(BaseModel):
    """Describes the body returned by the health endpoint.

    Exists as the contract of `GET /health`, which belongs to the application itself and
    not to any vertical. Consumed by `bia/api/main.py`.
    """

    status: HealthStatus
