from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import Connection, Uuid, column, table

from bia.agents.artifacts import AgentKind, AgentStatus

_EMBEDDING_DIMENSIONS = 1536
_AGENTS = table(
    "agents",
    column("id", Uuid),
    column("name"),
    column("description"),
    column("owner_area"),
    column("creator"),
    column("status"),
    column("kind"),
    column("description_embedding", Vector(_EMBEDDING_DIMENSIONS)),
)


def unit_vector(axis: int) -> list[float]:
    """Builds a vector pointing along one axis, so similarities have exact expected values.

    Args:
        axis: The position of the only non-zero value.

    Returns:
        list[float]: the vector, at the dimensions of the schema.
    """
    vector = [0.0] * _EMBEDDING_DIMENSIONS
    vector[axis] = 1.0
    return vector


def insert_registered_agent(connection: Connection, embedding: list[float] | None) -> UUID:
    """Inserts a published agent of an employee, without going through the gate.

    Args:
        connection: The connection of the test's transaction.
        embedding: The vector of its description, or None if it has not been generated.

    Returns:
        UUID: the identifier of the agent.
    """
    agent_id = uuid4()
    connection.execute(
        _AGENTS.insert().values(
            id=agent_id,
            name="Asistente",
            description="Responde dudas de facturas",
            owner_area="Servicio",
            creator="pytest",
            status=AgentStatus.PUBLISHED,
            kind=AgentKind.USER,
            description_embedding=embedding,
        )
    )
    return agent_id


def hide_published_agents(connection: Connection) -> None:
    """Moves the existing agents of employees out of the search, inside the test's transaction.

    Exists because a shared database may hold published agents, which would take the top places.

    Args:
        connection: The connection of the test's transaction.

    Returns:
        None: the rows are updated, and rolled back with the test.
    """
    connection.execute(
        _AGENTS.update().where(_AGENTS.c.kind == AgentKind.USER).values(status=AgentStatus.DRAFT)
    )
