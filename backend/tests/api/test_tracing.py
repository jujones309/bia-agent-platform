from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import sentinel
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from bia.agents.repository import AgentNotFoundError
from bia.api import tracing as tracing_router
from bia.api.dependencies import get_session
from bia.api.main import app
from bia.tracing.artifacts import (
    AgentMetrics,
    RunOrigin,
    RunRecord,
    RunStatus,
    RunStepRecord,
    StepType,
)
from bia.tracing.repository import RunNotFoundError


def _run_with_one_step() -> RunRecord:
    """Builds a finished run, as the repository would return it.

    Returns:
        RunRecord: the run, with one failed tool step.
    """
    run_id = uuid4()
    now = datetime.now(UTC)
    step = RunStepRecord(
        id=uuid4(),
        run_id=run_id,
        step_order=1,
        step_type=StepType.TOOL_CALL,
        model_id=None,
        tool_id=None,
        input={"numero_cliente": "100001"},
        output=None,
        input_tokens=0,
        output_tokens=0,
        cost=Decimal(0),
        latency_ms=4,
        error="Sin datos",
        created_at=now,
    )
    return RunRecord(
        id=run_id,
        agent_id=uuid4(),
        agent_version_id=uuid4(),
        origin=RunOrigin.PLAYGROUND,
        input="¿Cuál es mi saldo?",
        output=None,
        status=RunStatus.FAILED,
        error="Sin datos",
        total_tokens=0,
        total_cost=Decimal(0),
        latency_ms=12,
        started_at=now,
        finished_at=now,
        steps=[step],
    )


def _record_list_call(
    monkeypatch: pytest.MonkeyPatch, runs: list[RunRecord]
) -> list[tuple[UUID | None, int]]:
    """Replaces the repository read, recording the filters it receives.

    Args:
        monkeypatch: The patcher of the current test.
        runs: The runs the read returns.

    Returns:
        list[tuple[UUID | None, int]]: the agent and limit of each call, filled as they happen.
    """
    calls: list[tuple[UUID | None, int]] = []
    app.dependency_overrides[get_session] = lambda: sentinel.session
    monkeypatch.setattr(
        tracing_router,
        "list_runs",
        lambda _session, agent_id, limit: calls.append((agent_id, limit)) or runs,
    )
    return calls


def test_runs_returns_each_run_with_its_steps_and_forwards_the_agent(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the body carries the trace of the steps and the filter reaches the read."""
    run = _run_with_one_step()
    calls = _record_list_call(monkeypatch, [run])

    response = api_client.get("/runs", params={"agent_id": str(run.agent_id)})

    assert response.status_code == 200
    assert calls == [(run.agent_id, 50)]
    body = response.json()[0]
    assert body["status"] == "failed"
    assert body["steps"][0]["step_type"] == "tool_call"
    assert body["steps"][0]["error"] == "Sin datos"


def test_runs_without_agent_lists_every_agent(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the filter is optional and the caller can choose the limit."""
    calls = _record_list_call(monkeypatch, [])

    response = api_client.get("/runs", params={"limit": 3})

    assert response.json() == []
    assert calls == [(None, 3)]


@pytest.mark.parametrize("params", [{"agent_id": "not-a-uuid"}, {"limit": 0}, {"limit": 201}])
def test_runs_rejects_invalid_filters(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch, params: dict[str, object]
) -> None:
    """Verifies a bad filter or an oversized page never reaches the database."""
    calls = _record_list_call(monkeypatch, [])

    assert api_client.get("/runs", params=params).status_code == 422
    assert calls == []


def test_run_by_id_returns_that_run_with_its_steps(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the trace of an answer opens from its identifier alone."""
    run = _run_with_one_step()
    app.dependency_overrides[get_session] = lambda: sentinel.session
    monkeypatch.setattr(
        tracing_router, "get_run", lambda _session, run_id: run if run_id == run.id else None
    )

    response = api_client.get(f"/runs/{run.id}")

    assert response.status_code == 200
    assert response.json()["id"] == str(run.id)
    assert response.json()["steps"][0]["latency_ms"] == 4


def test_run_by_id_answers_404_when_it_does_not_exist(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies a stale link gets a clear error and not a server failure."""
    app.dependency_overrides[get_session] = lambda: sentinel.session
    monkeypatch.setattr(tracing_router, "get_run", _raise_run_not_found)

    assert api_client.get(f"/runs/{uuid4()}").status_code == 404


def _raise_run_not_found(_session: object, run_id: UUID) -> RunRecord:
    """Simulates a read of a run that does not exist.

    Args:
        _session: The session the read would have used.
        run_id: The identifier that was looked up.

    Returns:
        RunRecord: it never returns; it always raises.
    """
    raise RunNotFoundError(f"There is no run with id {run_id}")


def test_metrics_returns_the_aggregates_of_the_requested_agent(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the path identifier selects the agent and the numbers reach the body."""
    agent_id = uuid4()
    app.dependency_overrides[get_session] = lambda: sentinel.session
    monkeypatch.setattr(
        tracing_router,
        "get_agent_metrics",
        lambda _session, requested_id, _origin: AgentMetrics(
            agent_id=requested_id,
            total_runs=4,
            total_cost=Decimal("0.35"),
            latency_p50_ms=200.0,
            error_rate=0.25,
        ),
    )

    response = api_client.get(f"/agents/{agent_id}/metrics")

    assert response.status_code == 200
    body = response.json()
    assert body["agent_id"] == str(agent_id)
    assert (body["total_runs"], body["latency_p50_ms"], body["error_rate"]) == (4, 200.0, 0.25)
    assert float(body["total_cost"]) == 0.35


def _raise_agent_not_found(_session: object, agent_id: UUID, _origin: object) -> AgentMetrics:
    """Fails as the repository does for an agent that does not exist.

    Args:
        _session: The unused session of the request.
        agent_id: The requested agent.
        _origin: The unused origin filter.

    Returns:
        AgentMetrics: never; declared to match the replaced function.

    Raises:
        AgentNotFoundError: Always.
    """
    raise AgentNotFoundError(f"There is no agent with id {agent_id}")


def test_metrics_forwards_the_origin_and_rejects_an_unknown_one(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the filter reaches the read, and a typo is not an empty result."""
    agent_id = uuid4()
    origins: list[RunOrigin | None] = []
    app.dependency_overrides[get_session] = lambda: sentinel.session
    monkeypatch.setattr(
        tracing_router,
        "get_agent_metrics",
        lambda _session, requested_id, origin: (
            origins.append(origin)
            or AgentMetrics(
                agent_id=requested_id,
                total_runs=0,
                total_cost=Decimal(0),
                latency_p50_ms=None,
                error_rate=None,
            )
        ),
    )

    api_client.get(f"/agents/{agent_id}/metrics", params={"origin": "production"})
    rejected = api_client.get(f"/agents/{agent_id}/metrics", params={"origin": "typo"})

    assert origins == [RunOrigin.PRODUCTION]
    assert rejected.status_code == 422


def test_metrics_answers_404_for_an_unknown_agent(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies a missing agent is a client error that names the identifier, not a 500."""
    missing_id = uuid4()
    app.dependency_overrides[get_session] = lambda: sentinel.session
    monkeypatch.setattr(tracing_router, "get_agent_metrics", _raise_agent_not_found)

    response = api_client.get(f"/agents/{missing_id}/metrics")

    assert response.status_code == 404
    assert str(missing_id) in response.json()["detail"]


@pytest.mark.parametrize("path", ["/runs", f"/agents/{uuid4()}/metrics"])
def test_tracing_requires_credentials(path: str) -> None:
    """Verifies the audit record stays behind the shared password."""
    assert TestClient(app).get(path).status_code == 401
