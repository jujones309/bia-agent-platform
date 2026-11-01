from contextlib import nullcontext
from unittest.mock import sentinel

import pytest
from fastapi.testclient import TestClient

from bia.api import main
from bia.api.main import app


def test_health_reports_ok_status() -> None:
    """Verifies the health endpoint answers 200 with the exact agreed body."""
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_browser_preflight_from_the_frontend_is_allowed_without_credentials() -> None:
    """Verifies the preflight reaches an answer, since a browser never sends credentials on it."""
    response = TestClient(app).options(
        "/agents",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


def test_preflight_from_an_unknown_site_is_not_allowed() -> None:
    """Verifies another site cannot call the API from a visitor's browser."""
    response = TestClient(app).options(
        "/agents",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_rejected_request_stays_readable_by_the_frontend() -> None:
    """Verifies a wrong password reaches the login form as a 401 and not as a network failure."""
    response = TestClient(app).get("/agents", headers={"Origin": "http://localhost:3000"})

    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_every_route_still_requires_credentials_from_an_allowed_origin() -> None:
    """Verifies an allowed origin alone grants no access to the API."""
    response = TestClient(app).post("/agents", headers={"Origin": "http://localhost:3000"})

    assert response.status_code == 401


def _replace_database_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """Makes the startup open a placeholder session instead of reaching a database.

    Args:
        monkeypatch: The fixture that restores the module after the test.

    Returns:
        None: the module is patched in place.
    """
    monkeypatch.setattr(main, "get_engine", lambda: sentinel.engine)
    monkeypatch.setattr(main, "database_session", lambda _engine: nullcontext(sentinel.session))


def test_startup_syncs_tools_system_agents_and_builder_flow_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies all is in place for the first request, with the agents before their flow."""
    synced: list[str] = []
    _replace_database_session(monkeypatch)
    monkeypatch.setattr(main, "sync_tools", lambda _session: synced.append("tools"))
    monkeypatch.setattr(main, "sync_system_agents", lambda _session: synced.append("agents"))
    monkeypatch.setattr(main, "sync_builder_flow", lambda _session: synced.append("flow"))

    with TestClient(app) as client:
        assert synced == ["tools", "agents", "flow"]
        assert client.get("/health").status_code == 200


def test_startup_fails_when_the_tool_catalog_cannot_be_synced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies a failed sync aborts the startup instead of being swallowed."""
    _replace_database_session(monkeypatch)
    monkeypatch.setattr(main, "sync_tools", _raise_database_down)

    with pytest.raises(ConnectionError, match="database down"), TestClient(app):
        pass


def test_startup_fails_when_the_system_agents_cannot_be_synced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies the API does not serve a builder that could not be registered."""
    _replace_database_session(monkeypatch)
    monkeypatch.setattr(main, "sync_tools", lambda _session: None)
    monkeypatch.setattr(main, "sync_system_agents", _raise_database_down)

    with pytest.raises(ConnectionError, match="database down"), TestClient(app):
        pass


def _raise_database_down(_session: object) -> None:
    """Simulates a sync that cannot reach the database.

    Args:
        _session: The session the sync would have used.

    Returns:
        None: it always raises.
    """
    raise ConnectionError("database down")
