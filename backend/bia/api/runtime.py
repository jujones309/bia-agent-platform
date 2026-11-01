from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import Engine

from bia.agents.repository import ActiveVersionNotFoundError
from bia.api.dependencies import get_database_engine
from bia.runtime.artifacts import AgentRunRequest, AgentRunResult
from bia.runtime.conversations import (
    ConversationNotOpenError,
    continue_conversation,
    finish_conversation,
    start_conversation,
)
from bia.runtime.execution import AgentConfigurationError
from bia.tracing.artifacts import RunRecord
from bia.tracing.recorder import RunNotRunningError
from bia.tracing.repository import RunNotFoundError

router = APIRouter(tags=["runtime"])


def _send_message(engine: Engine, agent_id: UUID, request: AgentRunRequest) -> AgentRunResult:
    """Starts a conversation or continues the one the request names.

    Exists to keep that choice out of the error translation of the endpoint.

    Args:
        engine: The engine to read and trace through.
        agent_id: The agent to talk to.
        request: The body with the user's input and, if any, the open run.

    Returns:
        AgentRunResult: the answer, or why there is none, with the run identifier.
    """
    if request.run_id is None:
        return start_conversation(engine, agent_id, request.input)
    return continue_conversation(engine, agent_id, request.run_id, request.input)


@router.post("/agents/{agent_id}/run", response_model=AgentRunResult)
def run_in_playground(
    agent_id: UUID,
    request: AgentRunRequest,
    engine: Annotated[Engine, Depends(get_database_engine)],
) -> AgentRunResult:
    """Sends a message to an agent from the playground, within one run that stays open.

    Exists so a person can hold a conversation with an agent and open its trace; served as
    `POST /agents/{id}/run`. Without `run_id` it opens a new run. A turn without an answer
    answers 200 with the reason in `error`, because the request did execute and the run can go on.

    Args:
        agent_id: The agent to execute.
        request: The body with the user's input and, to continue, the open run.
        engine: The engine to read and trace through.

    Returns:
        AgentRunResult: the answer, or why there is none, with the run identifier.

    Raises:
        HTTPException: A 404 if the agent has no version to run or the run does not exist, or a
            409 if the run cannot continue or the spec references an unavailable model or tool.
    """
    try:
        return _send_message(engine, agent_id, request)
    except (ActiveVersionNotFoundError, RunNotFoundError) as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except (AgentConfigurationError, ConversationNotOpenError, RunNotRunningError) as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error


@router.post("/runs/{run_id}/finish", response_model=RunRecord)
def finish_playground_run(
    run_id: UUID, engine: Annotated[Engine, Depends(get_database_engine)]
) -> RunRecord:
    """Finishes an open conversation; the next message to the agent will open a new run.

    Exists because only the person knows when a conversation is over; served as
    `POST /runs/{id}/finish`.

    Args:
        run_id: The conversation to finish.
        engine: The engine to read and trace through.

    Returns:
        RunRecord: the closed run, with its totals and its steps.

    Raises:
        HTTPException: A 404 if the run does not exist, or a 409 if it is not an open conversation.
    """
    try:
        return finish_conversation(engine, run_id)
    except RunNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except (ConversationNotOpenError, RunNotRunningError) as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
