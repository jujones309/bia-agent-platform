from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from bia.agents.artifacts import AgentVersion
from bia.database.queries import DatabaseTable, SqlOperation, load_sql


class ActiveVersionNotFoundError(LookupError):
    """Signals that an agent cannot be executed because it has no version to run.

    Exists so a wrong identifier is told apart from a database failure. Raised by
    `get_active_version` and translated to a 404 by `bia/api/runtime.py`.
    """


def get_active_version(session: Session, agent_id: UUID) -> AgentVersion:
    """Retrieves the version an agent currently executes.

    Exists so the runtime always runs the version the registry points to; used by
    `load_agent_execution`.

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
