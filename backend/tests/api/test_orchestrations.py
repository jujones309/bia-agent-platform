from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from bia.api import orchestrations as orchestrations_router
from bia.api.dependencies import get_session
from bia.api.main import app
from bia.orchestrations.flows import ProtectedFlowError
from bia.orchestrations.repository import OrchestrationNotFoundError


@pytest.fixture
def client(api_client: TestClient) -> TestClient:
    """Provides an authenticated client that never reaches a real database.

    Args:
        api_client: The authenticated client.

    Returns:
        TestClient: the client.
    """
    app.dependency_overrides[get_session] = lambda: None
    return api_client


class _Raiser:
    """Stands for a retirement that fails; a class because nested functions are banned."""

    def __init__(self, error: Exception) -> None:
        """Keeps the error.

        Args:
            error (Exception): The error to raise when called.
        """
        self._error = error

    def __call__(self, _session: object, _orchestration_id: UUID) -> None:
        """Raises the kept error.

        Args:
            _session: The unused session.
            _orchestration_id: The unused identifier.

        Returns:
            None: never.

        Raises:
            Exception: The kept error.
        """
        raise self._error


def test_delete_retires_the_requested_flow_and_answers_without_a_body(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the route retires the flow in the path."""
    retired: list[UUID] = []
    monkeypatch.setattr(
        orchestrations_router,
        "retire_registered_flow",
        lambda _session, flow_id: retired.append(flow_id),
    )
    flow_id = uuid4()

    response = client.delete(f"/orchestrations/{flow_id}")

    assert response.status_code == 204
    assert response.content == b""
    assert retired == [flow_id]


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (OrchestrationNotFoundError("There is no flow"), 404),
        (ProtectedFlowError("It belongs to the platform"), 409),
    ],
)
def test_delete_translates_each_failure_with_its_explanation(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected_status: int,
) -> None:
    """Verifies each failure reaches the person with its own status and reason."""
    monkeypatch.setattr(orchestrations_router, "retire_registered_flow", _Raiser(error))

    response = client.delete(f"/orchestrations/{uuid4()}")

    assert response.status_code == expected_status
    assert response.json()["detail"] == str(error)


def test_a_browser_may_send_a_delete(client: TestClient) -> None:
    """Verifies the preflight allows the method, or the frontend's buttons could never work."""
    response = client.options(
        f"/orchestrations/{uuid4()}",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "DELETE",
        },
    )

    assert response.status_code == 200
    assert "DELETE" in response.headers["access-control-allow-methods"]
