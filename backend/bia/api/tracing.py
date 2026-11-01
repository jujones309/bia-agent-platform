from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from bia.agents.repository import AgentNotFoundError
from bia.api.dependencies import get_session
from bia.tracing.artifacts import AgentMetrics, RunOrigin, RunRecord
from bia.tracing.repository import get_agent_metrics, list_runs

_DEFAULT_RUNS_LIMIT = 50
_MAX_RUNS_LIMIT = 200

router = APIRouter(tags=["tracing"])


@router.get("/runs", response_model=list[RunRecord])
def get_runs(
    session: Annotated[Session, Depends(get_session)],
    agent_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=_MAX_RUNS_LIMIT)] = _DEFAULT_RUNS_LIMIT,
) -> list[RunRecord]:
    """Lists the most recent runs, each with its steps.

    Exists so people and the frontend can audit what agents did; served as `GET /runs`. The
    limit is capped because each step stores complete inputs and outputs.

    Args:
        session: The session of the request.
        agent_id: The agent whose runs are wanted; every agent's when omitted.
        limit: The maximum number of runs to return.

    Returns:
        list[RunRecord]: the matching runs, newest first.
    """
    return list_runs(session, agent_id, limit)


@router.get("/agents/{agent_id}/metrics", response_model=AgentMetrics)
def get_metrics(
    agent_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    origin: RunOrigin | None = None,
) -> AgentMetrics:
    """Retrieves the aggregated metrics of an agent.

    Exists so an agent's cost, speed and reliability can be read at a glance; served as
    `GET /agents/{id}/metrics`.

    Args:
        agent_id: The agent to summarize.
        session: The session of the request.
        origin: The only origin to count; every origin when omitted.

    Returns:
        AgentMetrics: the aggregates of the agent's runs.

    Raises:
        HTTPException: A 404 if no agent has that identifier.
    """
    try:
        return get_agent_metrics(session, agent_id, origin)
    except AgentNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
