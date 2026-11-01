from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from bia.agents.artifacts import (
    Agent,
    AgentDetail,
    AgentDraft,
    AgentIdentityPatch,
    AgentSpecPatch,
    AgentVersion,
)
from bia.agents.registry import (
    AgentNotManageableError,
    UnchangedAgentIdentityError,
    activate_version,
    add_version,
    archive_agent,
    create_agent,
    get_agent_detail,
    update_identity,
)
from bia.agents.repository import (
    ActiveVersionNotFoundError,
    AgentNotFoundError,
    AgentVersionNotFoundError,
    get_agent,
    list_agents,
    list_versions,
)
from bia.agents.validation import InvalidAgentSpecError
from bia.api.dependencies import get_database_engine, get_session
from bia.catalog.models.repository import EmbeddingModelUnavailableError
from bia.providers.base import ProviderError

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=list[Agent])
def get_agents(session: Annotated[Session, Depends(get_session)]) -> list[Agent]:
    """Lists the registry of agents.

    Exists so people and the frontend can see which agents exist; served as `GET /agents`.

    Args:
        session: The session of the request.

    Returns:
        list[Agent]: every agent, newest first.
    """
    return list_agents(session)


@router.post("", response_model=AgentDetail, status_code=status.HTTP_201_CREATED)
def post_agent(
    draft: AgentDraft, engine: Annotated[Engine, Depends(get_database_engine)]
) -> AgentDetail:
    """Creates an agent in draft with its version 1.

    Exists as the manual way to register an agent; served as `POST /agents`. Uses the engine
    because a request-scoped session would stay open during the embedding call.

    Args:
        draft: The identity of the agent and its first spec.
        engine: The engine to read, write and trace through.

    Returns:
        AgentDetail: the new agent with its version.

    Raises:
        HTTPException: A 422 if the spec references anything unavailable, a 502 if the
            embedding call fails, or a 503 if the catalog has no embedding model.
    """
    try:
        return create_agent(engine, draft)
    except InvalidAgentSpecError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    except ProviderError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error
    except EmbeddingModelUnavailableError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error


@router.get("/{agent_id}", response_model=AgentDetail)
def get_agent_by_id(
    agent_id: UUID, session: Annotated[Session, Depends(get_session)]
) -> AgentDetail:
    """Retrieves an agent with the version it currently executes.

    Exists so a person can review an agent's spec; served as `GET /agents/{id}`.

    Args:
        agent_id: The agent to look up.
        session: The session of the request.

    Returns:
        AgentDetail: the agent and its active version.

    Raises:
        HTTPException: A 404 if no agent has that identifier.
    """
    try:
        return get_agent_detail(session, agent_id)
    except AgentNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error


@router.patch("/{agent_id}", response_model=AgentDetail)
def patch_agent(
    agent_id: UUID,
    patch: AgentSpecPatch,
    session: Annotated[Session, Depends(get_session)],
) -> AgentDetail:
    """Changes an agent's spec, creating a version that becomes the active one.

    Exists so a person can adjust a spec without losing its history; served as
    `PATCH /agents/{id}`.

    Args:
        agent_id: The agent to change.
        patch: The fields of the spec to change.
        session: The session of the request.

    Returns:
        AgentDetail: the agent with its new version.

    Raises:
        HTTPException: A 404 if the agent or its active version does not exist, or a 422 if the
            resulting spec is invalid or changes nothing.
    """
    try:
        return add_version(session, agent_id, patch)
    except (AgentNotFoundError, ActiveVersionNotFoundError) as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except InvalidAgentSpecError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error


@router.patch("/{agent_id}/identity", response_model=AgentDetail)
def patch_agent_identity(
    agent_id: UUID,
    patch: AgentIdentityPatch,
    engine: Annotated[Engine, Depends(get_database_engine)],
) -> AgentDetail:
    """Changes the name, description or area of an agent.

    Exists because these are not part of the versioned spec; served as
    `PATCH /agents/{id}/identity`. Uses the engine because a request-scoped session would stay open
    during the embedding call.

    Args:
        agent_id: The agent to change.
        patch: The fields to change.
        engine: The engine to read, write and trace through.

    Returns:
        AgentDetail: the agent with its new identity.

    Raises:
        HTTPException: A 404 if the agent or its version does not exist, a 409 if it is a system or
            archived agent, a 422 if nothing changes, a 502 if the embedding call fails, or a 503
            if the catalog has no embedding model.
    """
    try:
        return update_identity(engine, agent_id, patch)
    except (AgentNotFoundError, ActiveVersionNotFoundError) as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except AgentNotManageableError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except UnchangedAgentIdentityError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    except ProviderError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error
    except EmbeddingModelUnavailableError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error


@router.post("/{agent_id}/archive", response_model=AgentDetail)
def post_archive(agent_id: UUID, session: Annotated[Session, Depends(get_session)]) -> AgentDetail:
    """Archives an agent, which leaves the duplicate search and keeps its traces.

    Exists so an agent can be retired without SQL; served as `POST /agents/{id}/archive`.

    Args:
        agent_id: The agent to archive.
        session: The session of the request.

    Returns:
        AgentDetail: the archived agent.

    Raises:
        HTTPException: A 404 if no agent has that identifier, or a 409 if it is a system agent.
    """
    try:
        return archive_agent(session, agent_id)
    except AgentNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except AgentNotManageableError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error


@router.get("/{agent_id}/versions", response_model=list[AgentVersion])
def get_versions(
    agent_id: UUID, session: Annotated[Session, Depends(get_session)]
) -> list[AgentVersion]:
    """Lists the history of an agent's versions.

    Exists so a person can choose a version to roll back to; served as
    `GET /agents/{id}/versions`.

    Args:
        agent_id: The agent to look up.
        session: The session of the request.

    Returns:
        list[AgentVersion]: its versions, oldest first.

    Raises:
        HTTPException: A 404 if no agent has that identifier.
    """
    try:
        get_agent(session, agent_id)
    except AgentNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    return list_versions(session, agent_id)


@router.post("/{agent_id}/versions/{version_number}/activate", response_model=AgentDetail)
def post_activate_version(
    agent_id: UUID,
    version_number: int,
    session: Annotated[Session, Depends(get_session)],
) -> AgentDetail:
    """Rolls an agent to an existing version.

    Exists to undo a bad change; served as `POST /agents/{id}/versions/{n}/activate`.

    Args:
        agent_id: The agent to change.
        version_number: The number of the version to activate.
        session: The session of the request.

    Returns:
        AgentDetail: the agent with that version.

    Raises:
        HTTPException: A 404 if the agent or the version does not exist, or a 409 if the
            version names a tool that is no longer available.
    """
    try:
        return activate_version(session, agent_id, version_number)
    except (AgentNotFoundError, AgentVersionNotFoundError) as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except InvalidAgentSpecError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
