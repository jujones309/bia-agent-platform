import logging
from uuid import UUID

from sqlalchemy import Connection, Engine
from sqlalchemy.orm import Session

from bia.agents.artifacts import AgentDetail, AgentDraft, AgentSpecPatch, AgentVersion
from bia.agents.repository import (
    ActiveVersionNotFoundError,
    get_active_version,
    get_agent,
    get_version,
    insert_agent,
    insert_version,
    lock_agent,
    set_active_version,
)
from bia.agents.validation import merge_spec_patch, validate_new_spec, validate_rollback_spec
from bia.catalog.models.artifacts import CatalogModel, ModelSize
from bia.catalog.models.repository import list_catalog_models
from bia.database.connection import database_session
from bia.providers.artifacts import EmbeddingResult
from bia.providers.cost import compute_cost
from bia.providers.factory import get_provider
from bia.tracing.artifacts import RunOrigin, RunStepDraft, StepType
from bia.tracing.recorder import RunRecorder

logger = logging.getLogger(__name__)


class EmbeddingModelUnavailableError(LookupError):
    """Signals that the model catalog has no active embedding model.

    Exists because a new agent cannot be found by duplicate detection without its embedding.
    Raised by `_find_embedding_model` and translated to a 503 by `bia/api/agents.py`.
    """


def _find_embedding_model(session: Session) -> CatalogModel:
    """Chooses the catalog model that embeds agent descriptions.

    Exists because model identifiers always come from the catalog; used by `create_agent`.

    Args:
        session: The open session to read the catalog through.

    Returns:
        CatalogModel: the first active embedding model, by name.

    Raises:
        EmbeddingModelUnavailableError: If the catalog has none.
    """
    for model in list_catalog_models(session, only_active=True):
        if model.size is ModelSize.EMBEDDING:
            return model
    raise EmbeddingModelUnavailableError("The model catalog has no active embedding model")


def _trace_embedding(
    bind: Engine | Connection,
    version: AgentVersion,
    description: str,
    model: CatalogModel,
    result: EmbeddingResult,
) -> None:
    """Records the embedding of a description as a closed run of the new agent.

    Exists because every LLM call is traced. It is written after creating the agent, since a run
    must reference one; used by `create_agent`.

    Args:
        bind: The database handle to trace through.
        version: The first version of the new agent.
        description: The text that was embedded.
        model: The model that embedded it.
        result: The outcome of the call.

    Returns:
        None: the run is written and closed.
    """
    recorder = RunRecorder(bind)
    run = recorder.start_run(version.agent_id, version.id, RunOrigin.BUILDER, description)
    dimensions = len(result.embeddings[0])
    recorder.add_step(
        run.id,
        RunStepDraft(
            step_type=StepType.LLM_CALL,
            model_id=model.id,
            input=[description],
            output={"embedding_dimensions": dimensions},
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            cost=compute_cost(result.usage, model),
            latency_ms=result.latency_ms,
        ),
    )
    recorder.finish_run(run.id, f"Embedding of {dimensions} dimensions")


def create_agent(bind: Engine | Connection, draft: AgentDraft) -> AgentDetail:
    """Creates an agent in draft with its first version and its description embedding.

    Exists as the single way to register an agent; used by the agents API. The embedding happens
    between two short transactions, so no connection stays open during the LLM call, and a
    failure leaves nothing half-created.

    Args:
        bind: The database handle to read, write and trace through.
        draft: The identity of the agent and the spec of its first version.

    Returns:
        AgentDetail: the new agent with its version 1.

    Raises:
        InvalidAgentSpecError: If the spec references anything unavailable.
        EmbeddingModelUnavailableError: If the catalog has no active embedding model.
        ProviderError: If the embedding call fails.
    """
    with database_session(bind) as session:
        validate_new_spec(session, draft.spec)
        model = _find_embedding_model(session)
    logger.info("Embedding the description of new agent '%s'", draft.name)
    result = get_provider(model.provider).embed([draft.description], model.provider_model_id)
    with database_session(bind) as session:
        agent = insert_agent(session, draft, result.embeddings[0])
        version = insert_version(session, agent.id, draft.spec)
    _trace_embedding(bind, version, draft.description, model, result)
    logger.info("Agent %s created in %s at version 1", agent.id, agent.status.value)
    return AgentDetail(agent=agent, active_version=version)


def add_version(session: Session, agent_id: UUID, patch: AgentSpecPatch) -> AgentDetail:
    """Applies a change to an agent's spec as a new version, which becomes the active one.

    Exists because versions are immutable: editing never overwrites. Used by the agents API.

    Args:
        session: The open session whose transaction contains the whole change.
        agent_id: The agent to change.
        patch: The fields of the spec to change.

    Returns:
        AgentDetail: the agent, pointing at its new version.

    Raises:
        AgentNotFoundError: If no agent has that identifier.
        ActiveVersionNotFoundError: If the agent has no version to start from.
        InvalidAgentSpecError: If the resulting spec is invalid or changes nothing.
    """
    lock_agent(session, agent_id)
    spec = merge_spec_patch(get_active_version(session, agent_id).spec, patch)
    validate_new_spec(session, spec)
    version = insert_version(session, agent_id, spec)
    agent = set_active_version(session, agent_id, version.version_number)
    logger.info("Agent %s moved to new version %d", agent_id, version.version_number)
    return AgentDetail(agent=agent, active_version=version)


def activate_version(session: Session, agent_id: UUID, version_number: int) -> AgentDetail:
    """Makes an existing version the one an agent executes.

    Exists so a bad change can be undone without writing anything new; used by the agents API.
    Activating the version already active changes nothing and is not an error.

    Args:
        session: The open session whose transaction contains the change.
        agent_id: The agent to change.
        version_number: The number of the version to activate.

    Returns:
        AgentDetail: the agent, pointing at that version.

    Raises:
        AgentNotFoundError: If no agent has that identifier.
        AgentVersionNotFoundError: If the agent has no version with that number.
        InvalidAgentSpecError: If the runtime could not execute that version.
    """
    lock_agent(session, agent_id)
    version = get_version(session, agent_id, version_number)
    validate_rollback_spec(session, version.spec)
    agent = set_active_version(session, agent_id, version_number)
    logger.info("Agent %s rolled to version %d", agent_id, version_number)
    return AgentDetail(agent=agent, active_version=version)


def get_agent_detail(session: Session, agent_id: UUID) -> AgentDetail:
    """Retrieves an agent with the version it currently executes.

    Exists so the read of `GET /agents/{id}` shows the spec too; used by the agents API.

    Args:
        session: The open session to read through.
        agent_id: The agent to look up.

    Returns:
        AgentDetail: the agent and its active version, if it has one.

    Raises:
        AgentNotFoundError: If no agent has that identifier.
    """
    agent = get_agent(session, agent_id)
    try:
        return AgentDetail(agent=agent, active_version=get_active_version(session, agent_id))
    except ActiveVersionNotFoundError:
        return AgentDetail(agent=agent, active_version=None)
