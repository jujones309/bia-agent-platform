from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Connection, Uuid, column, table

from bia.tracing.artifacts import RunOrigin, RunStatus


def _insert(connection: Connection, table_name: str, row: dict[str, object]) -> None:
    """Inserts one row into a table of the real schema.

    Args:
        connection: The connection of the test's transaction.
        table_name: The table to write to.
        row: The column values.

    Returns:
        None: the row is written inside the transaction.
    """
    columns = [column(name) for name in row]
    connection.execute(table(table_name, *columns).insert().values(row))


def insert_agent(connection: Connection) -> UUID:
    """Inserts an agent, so tracing tests can run before the agents vertical exists.

    Args:
        connection: The connection of the test's transaction.

    Returns:
        UUID: the identifier of the new agent.
    """
    agent_id = uuid4()
    _insert(
        connection,
        "agents",
        {
            "id": str(agent_id),
            "name": "Test agent",
            "description": "Answers test questions",
            "owner_area": "Tests",
            "creator": "pytest",
            "status": "draft",
            "kind": "user",
        },
    )
    return agent_id


def insert_agent_version(connection: Connection, agent_id: UUID) -> UUID:
    """Inserts the first version of an agent.

    Args:
        connection: The connection of the test's transaction.
        agent_id: The agent the version belongs to.

    Returns:
        UUID: the identifier of the new version.
    """
    version_id = uuid4()
    _insert(
        connection,
        "agent_versions",
        {"id": str(version_id), "agent_id": str(agent_id), "version_number": 1, "spec": "{}"},
    )
    return version_id


def insert_active_version(connection: Connection, agent_id: UUID, spec: str) -> UUID:
    """Inserts the first version of an agent and makes it the one that executes.

    Args:
        connection: The connection of the test's transaction.
        agent_id: The agent the version belongs to.
        spec: The spec, as a JSON document.

    Returns:
        UUID: the identifier of the new version.
    """
    version_id = uuid4()
    _insert(
        connection,
        "agent_versions",
        {"id": str(version_id), "agent_id": str(agent_id), "version_number": 1, "spec": spec},
    )
    agents = table("agents", column("id", Uuid), column("active_version_number"))
    connection.execute(
        agents.update().where(agents.c.id == agent_id).values(active_version_number=1)
    )
    return version_id


def insert_model(connection: Connection) -> UUID:
    """Inserts a catalog model that LLM call steps can reference.

    Args:
        connection: The connection of the test's transaction.

    Returns:
        UUID: the identifier of the new model.
    """
    model_id = uuid4()
    _insert(
        connection,
        "models",
        {
            "id": str(model_id),
            "name": "Test model",
            "provider": "openai",
            "provider_model_id": f"test-{model_id}",
            "size": "small",
            "input_cost_per_million": 1,
            "output_cost_per_million": 2,
            "context_window": 1000,
            "recommended_use": "Tests",
        },
    )
    return model_id


def insert_finished_run(
    connection: Connection,
    agent_id: UUID,
    version_id: UUID,
    status: RunStatus,
    latency_ms: int,
    total_cost: Decimal,
) -> None:
    """Inserts a closed run with fixed numbers, so aggregates have exact expected values.

    Args:
        connection: The connection of the test's transaction.
        agent_id: The agent of the run.
        version_id: The version of the run.
        status: The final status of the run.
        latency_ms: The duration of the run.
        total_cost: The cost of the run.

    Returns:
        None: the row is written inside the transaction.
    """
    _insert(
        connection,
        "runs",
        {
            "agent_id": str(agent_id),
            "agent_version_id": str(version_id),
            "origin": RunOrigin.PLAYGROUND,
            "input": "question",
            "status": status,
            "total_cost": total_cost,
            "latency_ms": latency_ms,
            "finished_at": "2026-10-31T00:00:00Z",
        },
    )
