import base64

import pytest
from fastapi.testclient import TestClient

from bia.api.main import app
from bia.settings.config import get_settings

client = TestClient(app)


def _basic_header(credentials: str) -> dict[str, str]:
    """Builds an HTTP Basic header from raw `username:password` credentials.

    Args:
        credentials: The text to encode as the header's credentials.

    Returns:
        dict[str, str]: the request headers carrying those credentials.
    """
    encoded = base64.b64encode(credentials.encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


def _valid_header() -> dict[str, str]:
    """Builds an HTTP Basic header with the configured password.

    Returns:
        dict[str, str]: the request headers that should grant access.
    """
    password = get_settings().api_access_password.get_secret_value()
    return _basic_header(f"any-user:{password}")


def test_health_stays_public() -> None:
    """Verifies uptime checks work without credentials."""
    assert client.get("/health").status_code == 200


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_documentation_requires_credentials(path: str) -> None:
    """Verifies Swagger and the schema are hidden, and browsers are asked to log in."""
    response = client.get(path)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"].startswith("Basic ")
    assert response.content == b""


@pytest.mark.parametrize("path", ["/docs", "/openapi.json"])
def test_documentation_opens_with_valid_password(path: str) -> None:
    """Verifies the demo flow: Swagger and its schema load with the shared password."""
    assert client.get(path, headers=_valid_header()).status_code == 200


def test_unknown_path_is_protected_by_default() -> None:
    """Verifies a route not on the allow-list is rejected before routing, not exposed."""
    assert client.post("/any/future/endpoint").status_code == 401
    assert client.post("/any/future/endpoint", headers=_valid_header()).status_code == 404


def test_public_path_match_is_exact() -> None:
    """Verifies the allow-list cannot be bypassed with a path that only starts like it."""
    assert client.get("/health/../docs/x").status_code == 401
    assert client.get("/healthcheck").status_code == 401


@pytest.mark.parametrize(
    "headers",
    [
        {"Authorization": "Bearer token"},
        {"Authorization": "Basic not-base64!"},
        {"Authorization": "Basic"},
        _basic_header("no-separator"),
        _basic_header("any-user:wrong-password"),
        _basic_header("any-user:"),
    ],
)
def test_invalid_credentials_are_rejected(headers: dict[str, str]) -> None:
    """Verifies wrong or malformed credentials get a 401 instead of a server error."""
    assert client.get("/docs", headers=headers).status_code == 401
