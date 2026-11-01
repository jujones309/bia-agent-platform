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


def _replace_database_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """Makes the startup open a placeholder session instead of reaching a database.

    Args:
        monkeypatch: The fixture that restores the module after the test.

    Returns:
        None: the module is patched in place.
    """
    monkeypatch.setattr(main, "get_engine", lambda: sentinel.engine)
    monkeypatch.setattr(main, "database_session", lambda _engine: nullcontext(sentinel.session))


def test_startup_syncs_tools_and_system_agents_before_serving(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies the catalog and the builder are in place by the time the first request arrives."""
    synced_tools: list[object] = []
    synced_agents: list[object] = []
    _replace_database_session(monkeypatch)
    monkeypatch.setattr(main, "sync_tools", synced_tools.append)
    monkeypatch.setattr(main, "sync_system_agents", synced_agents.append)

    with TestClient(app) as client:
        assert synced_tools == [sentinel.session]
        assert synced_agents == [sentinel.session]
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
