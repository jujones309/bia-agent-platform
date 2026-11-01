from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from bia.agents.repository import ActiveVersionNotFoundError
from bia.api import runtime as runtime_router
from bia.api.dependencies import get_database_engine
from bia.api.main import app
from bia.runtime.artifacts import AgentRunResult
from bia.runtime.execution import AgentConfigurationError
from bia.tracing.artifacts import RunOrigin, RunStatus


@pytest.fixture
def client(api_client: TestClient) -> TestClient:
    """Provides an authenticated client that never builds a real engine.

    Args:
        api_client: The authenticated client.

    Returns:
        TestClient: the client.
    """
    app.dependency_overrides[get_database_engine] = lambda: None
    return api_client


class _Raiser:
    """Stands for a `run_agent` that fails; a class because nested functions are not allowed."""

    def __init__(self, error: Exception) -> None:
        """Keeps the error.

        Args:
            error (Exception): The error to raise when called.
        """
        self._error = error

    def __call__(self, *_args: object) -> AgentRunResult:
        """Raises the kept error.

        Args:
            _args: The unused arguments of `run_agent`.

        Returns:
            AgentRunResult: never.

        Raises:
            Exception: The kept error.
        """
        raise self._error


def test_run_returns_the_answer_and_marks_the_origin(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the path and body select what runs, traced as a playground execution."""
    agent_id, run_id = uuid4(), uuid4()
    calls: list[tuple[UUID, str, RunOrigin]] = []
    result = AgentRunResult(run_id=run_id, status=RunStatus.SUCCEEDED, output="Hola", error=None)
    monkeypatch.setattr(
        runtime_router,
        "run_agent",
        lambda _bind, *args: calls.append(args) or result,
    )

    response = client.post(f"/agents/{agent_id}/run", json={"input": "hola"})

    assert response.status_code == 200
    assert response.json()["run_id"] == str(run_id)
    assert response.json()["output"] == "Hola"
    assert calls == [(agent_id, "hola", RunOrigin.PLAYGROUND)]


def test_failed_run_answers_200_with_the_trace_and_the_reason(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the caller can reach the trace of a run that failed."""
    run_id = uuid4()
    result = AgentRunResult(run_id=run_id, status=RunStatus.FAILED, output=None, error="Límite")
    monkeypatch.setattr(runtime_router, "run_agent", lambda *_args: result)

    body = client.post(f"/agents/{uuid4()}/run", json={"input": "hola"}).json()

    assert (body["status"], body["error"], body["run_id"]) == ("failed", "Límite", str(run_id))


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [(ActiveVersionNotFoundError("sin versión"), 404), (AgentConfigurationError("retirada"), 409)],
)
def test_agents_that_cannot_run_answer_a_client_error(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected_status: int,
) -> None:
    """Verifies these outcomes explain themselves instead of becoming a 500."""
    monkeypatch.setattr(runtime_router, "run_agent", _Raiser(error))

    response = client.post(f"/agents/{uuid4()}/run", json={"input": "hola"})

    assert response.status_code == expected_status
    assert response.json()["detail"] == str(error)


@pytest.mark.parametrize("body", [{}, {"input": ""}])
def test_run_rejects_an_empty_input(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, body: dict[str, str]
) -> None:
    """Verifies nothing is spent on a request with nothing to answer."""
    monkeypatch.setattr(runtime_router, "run_agent", _Raiser(AssertionError("must not run")))

    assert client.post(f"/agents/{uuid4()}/run", json=body).status_code == 422


def test_run_requires_credentials() -> None:
    """Verifies spending tokens stays behind the shared password."""
    assert TestClient(app).post(f"/agents/{uuid4()}/run", json={"input": "x"}).status_code == 401
