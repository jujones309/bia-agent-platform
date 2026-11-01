from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import Engine

from bia.agents.repository import ActiveVersionNotFoundError
from bia.api.dependencies import get_database_engine
from bia.runtime.artifacts import AgentRunRequest, AgentRunResult
from bia.runtime.execution import AgentConfigurationError
from bia.runtime.runner import run_agent
from bia.tracing.artifacts import RunOrigin

router = APIRouter(tags=["runtime"])


@router.post("/agents/{agent_id}/run", response_model=AgentRunResult)
def run_in_playground(
    agent_id: UUID,
    request: AgentRunRequest,
    engine: Annotated[Engine, Depends(get_database_engine)],
) -> AgentRunResult:
    """Executes an agent from the playground.

    Exists so a person can try an agent and open its trace; served as
    `POST /agents/{id}/run`. A run that fails answers 200 with status `failed`, because the
    request did execute and its body holds the `run_id` of the trace.

    Args:
        agent_id: The agent to execute.
        request: The body with the user's input.
        engine: The engine to read and trace through.

    Returns:
        AgentRunResult: the answer, or why there is none, with the run identifier.

    Raises:
        HTTPException: A 404 if the agent has no version to run, or a 409 if its spec
            references an unavailable model or tool.
    """
    try:
        return run_agent(engine, agent_id, request.input, RunOrigin.PLAYGROUND)
    except ActiveVersionNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except AgentConfigurationError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
