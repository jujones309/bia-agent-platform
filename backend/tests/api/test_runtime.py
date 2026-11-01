from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from bia.agents.repository import ActiveVersionNotFoundError
from bia.api import runtime as runtime_router
from bia.api.dependencies import get_database_engine
from bia.api.main import app
from bia.runtime.artifacts import AgentRunResult
from bia.runtime.conversations import ConversationNotOpenError
from bia.runtime.execution import AgentConfigurationError
from bia.tracing.artifacts import RunStatus
from bia.tracing.recorder import RunNotRunningError
from bia.tracing.repository import RunNotFoundError


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
    """Stands for a runtime function that fails; a class because nesting is not allowed."""

    def __init__(self, error: Exception) -> None:
        """Keeps the error.

        Args:
            error (Exception): The error to raise when called.
        """
        self._error = error

    def __call__(self, *_args: object) -> AgentRunResult:
        """Raises the kept error.

        Args:
            _args: The unused arguments of the runtime function.

        Returns:
            AgentRunResult: never.

        Raises:
            Exception: The kept error.
        """
        raise self._error


def test_run_without_a_run_id_starts_a_conversation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the path and body select what runs, in a new conversation."""
    agent_id, run_id = uuid4(), uuid4()
    calls: list[tuple[UUID, str]] = []
    result = AgentRunResult(run_id=run_id, status=RunStatus.SUCCEEDED, output="Hola", error=None)
    monkeypatch.setattr(
        runtime_router,
        "start_conversation",
        lambda _bind, *args: calls.append(args) or result,
    )

    response = client.post(f"/agents/{agent_id}/run", json={"input": "hola"})

    assert response.status_code == 200
    assert response.json()["run_id"] == str(run_id)
    assert response.json()["output"] == "Hola"
    assert calls == [(agent_id, "hola")]


def test_failed_run_answers_200_with_the_trace_and_the_reason(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the caller can reach the trace of a run that failed."""
    run_id = uuid4()
    result = AgentRunResult(run_id=run_id, status=RunStatus.FAILED, output=None, error="Límite")
    monkeypatch.setattr(runtime_router, "start_conversation", lambda *_args: result)

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
    monkeypatch.setattr(runtime_router, "start_conversation", _Raiser(error))

    response = client.post(f"/agents/{uuid4()}/run", json={"input": "hola"})

    assert response.status_code == expected_status
    assert response.json()["detail"] == str(error)


@pytest.mark.parametrize("body", [{}, {"input": ""}])
def test_run_rejects_an_empty_input(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, body: dict[str, str]
) -> None:
    """Verifies nothing is spent on a request with nothing to answer."""
    monkeypatch.setattr(
        runtime_router, "start_conversation", _Raiser(AssertionError("must not run"))
    )

    assert client.post(f"/agents/{uuid4()}/run", json=body).status_code == 422


def test_run_requires_credentials() -> None:
    """Verifies spending tokens stays behind the shared password."""
    assert TestClient(app).post(f"/agents/{uuid4()}/run", json={"input": "x"}).status_code == 401


def test_run_with_a_run_id_continues_that_conversation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies a follow-up goes to the open run instead of opening another one."""
    agent_id, run_id = uuid4(), uuid4()
    calls: list[tuple[UUID, UUID, str]] = []
    result = AgentRunResult(run_id=run_id, status=RunStatus.RUNNING, output="Dos", error=None)
    monkeypatch.setattr(runtime_router, "start_conversation", _Raiser(AssertionError("new run")))
    monkeypatch.setattr(
        runtime_router,
        "continue_conversation",
        lambda _bind, *args: calls.append(args) or result,
    )

    body = client.post(
        f"/agents/{agent_id}/run", json={"input": "otra", "run_id": str(run_id)}
    ).json()

    assert (body["status"], body["output"]) == ("running", "Dos")
    assert calls == [(agent_id, run_id, "otra")]


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (RunNotFoundError("no existe"), 404),
        (ConversationNotOpenError("finalizado"), 409),
        (RunNotRunningError("cerrado"), 409),
    ],
)
def test_messages_and_finishing_on_an_unusable_run_answer_a_client_error(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected_status: int,
) -> None:
    """Verifies a finished or unknown run explains itself, so the page can start a new one."""
    monkeypatch.setattr(runtime_router, "continue_conversation", _Raiser(error))
    monkeypatch.setattr(runtime_router, "finish_conversation", _Raiser(error))
    run_id = uuid4()

    message = client.post(f"/agents/{uuid4()}/run", json={"input": "x", "run_id": str(run_id)})
    finish = client.post(f"/runs/{run_id}/finish")

    assert (message.status_code, finish.status_code) == (expected_status, expected_status)
    assert finish.json()["detail"] == str(error)


def test_finish_requires_credentials() -> None:
    """Verifies closing a run stays behind the shared password."""
    assert TestClient(app).post(f"/runs/{uuid4()}/finish").status_code == 401
