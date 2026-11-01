from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import Engine

from bia.agents.repository import ActiveVersionNotFoundError
from bia.agents.validation import InvalidAgentSpecError
from bia.api.dependencies import get_database_engine
from bia.builder.artifacts import (
    AgentProposalRequest,
    AgentRequest,
    DuplicateCheckResult,
    ProposedAgent,
)
from bia.builder.designer.designer import propose_agent
from bia.builder.duplicates.judge import InvalidJudgeDecisionError, check_duplicates
from bia.catalog.models.repository import EmbeddingModelUnavailableError
from bia.providers.base import ProviderError
from bia.runtime.execution import AgentConfigurationError

router = APIRouter(prefix="/builder", tags=["builder"])


@router.post("/check", response_model=DuplicateCheckResult)
def post_check(
    request: AgentRequest, engine: Annotated[Engine, Depends(get_database_engine)]
) -> DuplicateCheckResult:
    """Checks whether a need is already covered by a published agent.

    Exists as the first step of creating an agent; served as `POST /builder/check`. Uses the engine
    because a request-scoped session would stay open during the LLM calls.

    Args:
        request: The described need.
        engine: The engine to read and trace through.

    Returns:
        DuplicateCheckResult: the verdict, with the chosen agent if there is one.

    Raises:
        HTTPException: A 502 if a model call fails or the judge's answer is unusable, or a 503 if
            the judge cannot run or the catalog has no embedding model.
    """
    try:
        return check_duplicates(engine, request)
    except (ProviderError, InvalidJudgeDecisionError) as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error
    except (
        ActiveVersionNotFoundError,
        AgentConfigurationError,
        EmbeddingModelUnavailableError,
    ) as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error


@router.post("/propose", response_model=ProposedAgent, status_code=status.HTTP_201_CREATED)
def post_propose(
    request: AgentProposalRequest, engine: Annotated[Engine, Depends(get_database_engine)]
) -> ProposedAgent:
    """Designs an agent for a need and creates it in draft.

    Exists so a person gets a complete spec to review, and adjust with `PATCH /agents/{id}`, without
    writing it; served as `POST /builder/propose`. Uses the engine because a request-scoped session
    would stay open during the LLM calls.

    Args:
        request: The described need and who will own the agent.
        engine: The engine to read, write and trace through.

    Returns:
        ProposedAgent: the new draft agent, with the reasons behind its spec.

    Raises:
        HTTPException: A 502 if a model call fails or the designer produced no valid spec, or a 503
            if the designer cannot run or the catalog has no embedding model.
    """
    try:
        return propose_agent(engine, request)
    except (ProviderError, InvalidAgentSpecError) as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error
    except (
        ActiveVersionNotFoundError,
        AgentConfigurationError,
        EmbeddingModelUnavailableError,
    ) as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error
