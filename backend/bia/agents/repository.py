import json
from uuid import UUID

from sqlalchemy import Result, text
from sqlalchemy.orm import Session

from bia.agents.artifacts import Agent, AgentDraft, AgentKind, AgentSpec, AgentStatus, AgentVersion
from bia.database.queries import DatabaseTable, SqlOperation, load_sql

_FIRST_VERSION_NUMBER = 1
_PLATFORM_OWNER_AREA = "Plataforma"
_PLATFORM_CREATOR = "bia-agent-platform"


class AgentNotFoundError(LookupError):
    """Signals that the registry has no agent with the requested identifier.

    Exists so an unknown agent is not confused with an agent without runs or versions. Raised
    by this repository and by `get_agent_metrics`, and translated to a 404 by `bia/api/`.
    """


class ActiveVersionNotFoundError(LookupError):
    """Signals that an agent cannot be executed because it has no version to run.

    Exists so a wrong identifier is told apart from a database failure. Raised by
    `get_active_version` and translated to a 404 by `bia/api/runtime.py`.
    """


class AgentVersionNotFoundError(LookupError):
    """Signals that an agent has no version with the requested number.

    Exists so a rollback to a wrong number fails clearly. Raised by `get_version` and
    translated to a 404 by `bia/api/agents.py`.
    """


def insert_agent(session: Session, draft: AgentDraft, description_embedding: list[float]) -> Agent:
    """Registers a user agent in draft, pointing at the first version it is about to get.

    Exists as the single write of new agents; used by `create_agent`, whose transaction also
    inserts that version.

    Args:
        session: The open session whose transaction contains the write.
        draft: The identity of the agent.
        description_embedding: The vector duplicate detection compares.

    Returns:
        Agent: the stored agent.
    """
    parameters = {
        "name": draft.name,
        "description": draft.description,
        "owner_area": draft.owner_area,
        "creator": draft.creator,
        "status": AgentStatus.DRAFT,
        "kind": AgentKind.USER,
        "description_embedding": json.dumps(description_embedding),
        "active_version_number": _FIRST_VERSION_NUMBER,
    }
    sql = load_sql(DatabaseTable.AGENTS, SqlOperation.INSERT)
    row = session.execute(text(sql), parameters).mappings().one()
    return Agent.model_validate(dict(row))


def get_agent(session: Session, agent_id: UUID) -> Agent:
    """Retrieves one agent of the registry.

    Exists to read an agent's identity; used by the registry and the agents API.

    Args:
        session: The open session to read through.
        agent_id: The agent to look up.

    Returns:
        Agent: the agent.

    Raises:
        AgentNotFoundError: If no agent has that identifier.
    """
    sql = load_sql(DatabaseTable.AGENTS, SqlOperation.GET_BY_ID)
    return _to_agent(session.execute(text(sql), {"agent_id": str(agent_id)}), agent_id)


def lock_agent(session: Session, agent_id: UUID) -> Agent:
    """Retrieves an agent and locks it until the transaction ends.

    Exists so concurrent changes to one agent happen one after the other; used by the registry
    before adding a version or changing the active one.

    Args:
        session: The open session whose transaction holds the lock.
        agent_id: The agent to lock.

    Returns:
        Agent: the agent, as it stands now that nobody else can change it.

    Raises:
        AgentNotFoundError: If no agent has that identifier.
    """
    sql = load_sql(DatabaseTable.AGENTS, SqlOperation.LOCK_BY_ID)
    return _to_agent(session.execute(text(sql), {"agent_id": str(agent_id)}), agent_id)


def list_agents(session: Session) -> list[Agent]:
    """Lists the registry of agents, newest first.

    Exists as the read behind the agent inventory; used by the agents API.

    Args:
        session: The open session to read through.

    Returns:
        list[Agent]: every agent.
    """
    rows = session.execute(text(load_sql(DatabaseTable.AGENTS, SqlOperation.LIST))).mappings()
    return [Agent.model_validate(dict(row)) for row in rows]


def set_active_version(session: Session, agent_id: UUID, version_number: int) -> Agent:
    """Changes the version an agent executes.

    Exists so that editing and rolling back share one write; used by the registry after
    locking the agent and checking that the version exists.

    Args:
        session: The open session whose transaction contains the write.
        agent_id: The agent to change.
        version_number: The number of the version to execute from now on.

    Returns:
        Agent: the updated agent.

    Raises:
        AgentNotFoundError: If no agent has that identifier.
    """
    sql = load_sql(DatabaseTable.AGENTS, SqlOperation.SET_ACTIVE_VERSION)
    parameters = {"agent_id": str(agent_id), "version_number": version_number}
    return _to_agent(session.execute(text(sql), parameters), agent_id)


def upsert_system_agent(session: Session, agent_id: UUID, name: str, description: str) -> None:
    """Registers a published part of the platform, or refreshes its name and description.

    Exists so the system agents follow the code, and so concurrent startups cannot duplicate them:
    their identifiers are fixed. Used by `sync_system_agents`, whose transaction also inserts the
    first version of a new one. They have no embedding, because they are never duplicates.

    Args:
        session: The open session whose transaction contains the write.
        agent_id: The fixed identifier of the system agent.
        name: The name shown in the inventories.
        description: What the agent does for the platform.

    Returns:
        None: the row is written inside the session's transaction.
    """
    parameters = {
        "agent_id": str(agent_id),
        "name": name,
        "description": description,
        "owner_area": _PLATFORM_OWNER_AREA,
        "creator": _PLATFORM_CREATOR,
        "status": AgentStatus.PUBLISHED,
        "kind": AgentKind.SYSTEM,
        "active_version_number": _FIRST_VERSION_NUMBER,
    }
    session.execute(text(load_sql(DatabaseTable.AGENTS, SqlOperation.UPSERT)), parameters)


def insert_version(
    session: Session,
    agent_id: UUID,
    spec: AgentSpec,
    designer_justification: str | None = None,
) -> AgentVersion:
    """Appends a version to an agent, at the next number of its sequence.

    Exists because a spec is never overwritten: every change is a new row. Used by the
    registry, which must have created or locked the agent in the same transaction.

    Args:
        session: The open session whose transaction contains the write.
        agent_id: The agent the version belongs to.
        spec: The validated spec.
        designer_justification: Why the designer proposed it; None if the version was manual.

    Returns:
        AgentVersion: the stored version, with its number.
    """
    sql = load_sql(DatabaseTable.AGENT_VERSIONS, SqlOperation.INSERT)
    parameters = {
        "agent_id": str(agent_id),
        "spec": spec.model_dump_json(),
        "designer_justification": designer_justification,
    }
    row = session.execute(text(sql), parameters).mappings().one()
    return AgentVersion.model_validate(dict(row))


def list_versions(session: Session, agent_id: UUID) -> list[AgentVersion]:
    """Lists the history of an agent's versions, oldest first.

    Exists so a person can compare versions and choose one to roll back to; used by the agents
    API.

    Args:
        session: The open session to read through.
        agent_id: The agent to look up.

    Returns:
        list[AgentVersion]: its versions; empty if it has none.
    """
    sql = load_sql(DatabaseTable.AGENT_VERSIONS, SqlOperation.LIST_BY_AGENT)
    rows = session.execute(text(sql), {"agent_id": str(agent_id)}).mappings()
    return [AgentVersion.model_validate(dict(row)) for row in rows]


def get_version(session: Session, agent_id: UUID, version_number: int) -> AgentVersion:
    """Retrieves one version of an agent from its number.

    Exists so a rollback resolves the number it received; used by `activate_version`.

    Args:
        session: The open session to read through.
        agent_id: The agent the version belongs to.
        version_number: The number within the agent.

    Returns:
        AgentVersion: the version.

    Raises:
        AgentVersionNotFoundError: If the agent has no version with that number.
    """
    sql = load_sql(DatabaseTable.AGENT_VERSIONS, SqlOperation.GET_BY_NUMBER)
    parameters = {"agent_id": str(agent_id), "version_number": version_number}
    row = session.execute(text(sql), parameters).mappings().one_or_none()
    if row is None:
        raise AgentVersionNotFoundError(f"Agent {agent_id} has no version {version_number}")
    return AgentVersion.model_validate(dict(row))


def get_active_version(session: Session, agent_id: UUID) -> AgentVersion:
    """Retrieves the version an agent currently executes.

    Exists so the runtime always runs the version the registry points to; used by
    `load_agent_execution` and by the registry.

    Args:
        session: The open session to read through.
        agent_id: The agent to look up.

    Returns:
        AgentVersion: the active version, with its validated spec.

    Raises:
        ActiveVersionNotFoundError: If the agent does not exist or has no active version.
    """
    sql = load_sql(DatabaseTable.AGENT_VERSIONS, SqlOperation.GET_ACTIVE)
    row = session.execute(text(sql), {"agent_id": str(agent_id)}).mappings().one_or_none()
    if row is None:
        raise ActiveVersionNotFoundError(f"Agent {agent_id} does not exist or has no version")
    return AgentVersion.model_validate(dict(row))


def _to_agent(result: Result, agent_id: UUID) -> Agent:
    """Converts the result of a query on one agent into its contract.

    Exists so every read and write of one agent fails the same way when it matches nothing.

    Args:
        result: The executed query.
        agent_id: The agent the query targeted.

    Returns:
        Agent: the agent.

    Raises:
        AgentNotFoundError: If the query matched no row.
    """
    row = result.mappings().one_or_none()
    if row is None:
        raise AgentNotFoundError(f"There is no agent with id {agent_id}")
    return Agent.model_validate(dict(row))
