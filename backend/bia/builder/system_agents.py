import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from bia.agents.artifacts import AgentSpec, AgentVersion
from bia.agents.repository import (
    ActiveVersionNotFoundError,
    get_active_version,
    insert_version,
    lock_agent,
    set_active_version,
    upsert_system_agent,
)
from bia.catalog.models.artifacts import ModelSize
from bia.catalog.models.repository import find_model_by_size
from bia.prompts.loader import PromptName, PromptVertical, load_prompt

logger = logging.getLogger(__name__)

DUPLICATE_JUDGE_AGENT_ID = UUID("5d0c6f2e-8a51-4f0b-9f1e-2f6a7b3c1d01")
DESIGNER_AGENT_ID = UUID("5d0c6f2e-8a51-4f0b-9f1e-2f6a7b3c1d02")


@dataclass(frozen=True)
class _SystemAgentDefinition:
    """Declares a part of the builder as an agent of the registry.

    Exists so the builder appears in the platform's own inventories and traces, with its prompts
    versioned like any other spec; consumed by `sync_system_agents`.
    """

    agent_id: UUID
    name: str
    description: str
    purpose: str
    prompt_vertical: PromptVertical
    prompt_name: PromptName
    model_size: ModelSize  # only applies when the agent is first registered


_DEFINITIONS = (
    _SystemAgentDefinition(
        agent_id=DUPLICATE_JUDGE_AGENT_ID,
        name="Juez de duplicados",
        description="Decide si una necesidad ya está cubierta por un agente publicado.",
        purpose="Evitar crear agentes que ya existen.",
        prompt_vertical=PromptVertical.BUILDER_DUPLICATES,
        prompt_name=PromptName.JUDGE,
        model_size=ModelSize.SMALL,  # a well-scoped classification over a few candidates
    ),
    _SystemAgentDefinition(
        agent_id=DESIGNER_AGENT_ID,
        name="Diseñador de agentes",
        description="Propone la spec de un agente nuevo, eligiendo solo de los catálogos.",
        purpose="Convertir una necesidad en lenguaje natural en una spec justificada.",
        prompt_vertical=PromptVertical.BUILDER_DESIGNER,
        prompt_name=PromptName.DESIGNER,
        model_size=ModelSize.LARGE,  # design decisions, where quality outweighs cost
    ),
)


def _register_first_version(session: Session, definition: _SystemAgentDefinition) -> None:
    """Gives a just-registered system agent its version 1.

    Exists to keep the choice of its initial model apart from later updates; used by
    `_sync_system_agent`.

    Args:
        session: The open session whose transaction contains the write.
        definition: The system agent.

    Returns:
        None: the version is written inside the session's transaction.

    Raises:
        ModelSizeUnavailableError: If the catalog has no model of the size it needs.
    """
    model = find_model_by_size(session, definition.model_size)
    spec = AgentSpec(
        purpose=definition.purpose,
        system_prompt=load_prompt(definition.prompt_vertical, definition.prompt_name),
        model_id=model.id,
    )
    insert_version(session, definition.agent_id, spec)
    logger.info("Registered system agent '%s' with model %s", definition.name, model.name)


def _update_when_outdated(
    session: Session, definition: _SystemAgentDefinition, active: AgentVersion
) -> None:
    """Adds a version if the code changed the prompt or the purpose of a system agent.

    Exists so prompt changes are versioned. The code owns the prompt and the purpose, while the
    active model is kept, so an operator can change it with `PATCH /agents/{id}`.

    Args:
        session: The open session whose transaction contains the write.
        definition: The system agent.
        active: The version it executes now.

    Returns:
        None: the version is written inside the session's transaction, if one is needed.
    """
    changes = {
        "purpose": definition.purpose,
        "system_prompt": load_prompt(definition.prompt_vertical, definition.prompt_name),
    }
    spec = active.spec.model_copy(update=changes)
    if spec == active.spec:
        return
    version = insert_version(session, definition.agent_id, spec)
    set_active_version(session, definition.agent_id, version.version_number)
    logger.info("System agent '%s' moved to version %d", definition.name, version.version_number)


def _sync_system_agent(session: Session, definition: _SystemAgentDefinition) -> None:
    """Makes the registry reflect one system agent.

    Exists to keep each agent's sync in one lock; used by `sync_system_agents`. The lock makes
    concurrent startups run this one after the other, so they cannot add the same version twice.

    Args:
        session: The open session whose transaction contains the sync.
        definition: The system agent.

    Returns:
        None: the registry is updated inside the session's transaction.

    Raises:
        ModelSizeUnavailableError: If the catalog has no model of the size it needs.
    """
    upsert_system_agent(session, definition.agent_id, definition.name, definition.description)
    lock_agent(session, definition.agent_id)
    try:
        active = get_active_version(session, definition.agent_id)
    except ActiveVersionNotFoundError:
        _register_first_version(session, definition)
        return
    _update_when_outdated(session, definition, active)


def sync_system_agents(session: Session) -> None:
    """Makes the registry reflect the parts of the builder.

    Exists because every LLM call is traced as a run, and a run must reference an agent; used at
    application startup by `bia/api/main.py`. It makes no LLM call: system agents have no
    description embedding because the duplicate search leaves them out.

    Args:
        session: The open session whose transaction contains the sync.

    Returns:
        None: the registry is updated inside the session's transaction.

    Raises:
        ModelSizeUnavailableError: If the catalog has no model of a size that is needed.
        PromptFileNotFoundError: If a prompt file is missing.
        InvalidPromptFileError: If a prompt file does not follow the conventions.
    """
    for definition in _DEFINITIONS:
        _sync_system_agent(session, definition)
    logger.info("Synced %d system agents to the registry", len(_DEFINITIONS))
