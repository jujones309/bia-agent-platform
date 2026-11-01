import json
from collections.abc import Iterator
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, Engine, Uuid, column, table, update

from bia.agents.artifacts import AgentKind, AgentStatus
from bia.catalog.models.artifacts import ModelSize
from bia.database.connection import database_session
from bia.database.migrate import apply_schema
from bia.inventory.artifacts import AgentInventoryItem, ModelInventoryItem
from bia.inventory.repository import (
    build_summary,
    get_inventory_summary,
    list_agent_inventory,
    list_model_inventory,
    list_orchestration_inventory,
)
from bia.orchestrations.artifacts import Flow, FlowStep, OrchestrationType
from bia.orchestrations.repository import save_flow
from bia.providers.artifacts import ProviderName
from bia.tracing.artifacts import RunStatus
from tests.tracing.seed import (
    insert_active_version,
    insert_agent,
    insert_finished_run,
    insert_model,
)

_AGENTS = table("agents", column("id", Uuid), column("status"), column("kind"))
_RUNS = table("runs", column("agent_id", Uuid), column("started_at"))
_RUN_STEPS = table(
    "run_steps",
    column("run_id"),
    column("step_order"),
    column("step_type"),
    column("model_id"),
    column("input"),
    column("output"),
    column("input_tokens"),
    column("output_tokens"),
    column("cost"),
    column("latency_ms"),
)
_KNOWLEDGE_BASES = table("knowledge_bases", column("id"), column("name"), column("description"))


@pytest.fixture
def connection(integration_engine: Engine) -> Iterator[Connection]:
    """Provides a connection with the schema, rolled back at the end.

    Args:
        integration_engine: The engine of the real database.

    Returns:
        Iterator[Connection]: yields the connection inside the open transaction.
    """
    with integration_engine.connect() as open_connection:
        transaction = open_connection.begin()
        with database_session(open_connection) as session:
            apply_schema(session)
        yield open_connection
        transaction.rollback()


def _insert_configured_agent(
    connection: Connection, model_id: UUID, tools: list[str] | None = None
) -> tuple[UUID, UUID]:
    """Inserts an agent whose active version uses a model and some tools.

    Args:
        connection: The connection of the test's transaction.
        model_id: The model of the spec.
        tools: The tools of the spec.

    Returns:
        tuple[UUID, UUID]: the identifiers of the agent and its version.
    """
    agent_id = insert_agent(connection)
    spec = json.dumps({"model_id": str(model_id), "tool_names": tools or []})
    return agent_id, insert_active_version(connection, agent_id, spec)


def _insert_run_with_step(
    connection: Connection, agent_id: UUID, version_id: UUID, model_id: UUID
) -> None:
    """Inserts a run with one LLM step of 10 input tokens, 5 output tokens and USD 0.1.

    Args:
        connection: The connection of the test's transaction.
        agent_id: The agent of the run.
        version_id: The version of the run.
        model_id: The model of the step.

    Returns:
        None: the rows are written inside the transaction.
    """
    insert_finished_run(connection, agent_id, version_id, RunStatus.SUCCEEDED, 10, Decimal("0.1"))
    runs = table("runs", column("id"), column("agent_id", Uuid), column("agent_version_id", Uuid))
    run_id = connection.execute(
        runs.select().where(runs.c.agent_version_id == version_id).order_by(runs.c.id).limit(1)
    ).first()[0]
    connection.execute(
        _RUN_STEPS.insert().values(
            run_id=run_id,
            step_order=1,
            step_type="llm_call",
            model_id=str(model_id),
            input="{}",
            output="{}",
            input_tokens=10,
            output_tokens=5,
            cost=Decimal("0.1"),
            latency_ms=1,
        )
    )


def test_agent_inventory_joins_spec_and_runs_without_multiplying(connection: Connection) -> None:
    """Verifies the row resolves names from the spec and adds up runs once each."""
    model_id = insert_model(connection)
    base_id = uuid4()
    connection.execute(
        _KNOWLEDGE_BASES.insert().values(id=str(base_id), name="Facturación", description="Docs")
    )
    agent_id = insert_agent(connection)
    spec = json.dumps(
        {
            "model_id": str(model_id),
            "tool_names": ["consultar_factura", "buscar_conocimiento"],
            "knowledge_base_id": str(base_id),
        }
    )
    version_id = insert_active_version(connection, agent_id, spec)
    for cost in ("0.1", "0.2"):
        insert_finished_run(connection, agent_id, version_id, RunStatus.SUCCEEDED, 5, Decimal(cost))

    with database_session(connection) as session:
        item = next(a for a in list_agent_inventory(session) if a.id == agent_id)

    assert (item.model_id, item.model_name) == (model_id, "Test model")
    assert item.tool_names == ["consultar_factura", "buscar_conocimiento"]
    assert (item.knowledge_base_id, item.knowledge_base_name) == (base_id, "Facturación")
    assert (item.total_runs, item.total_cost) == (2, Decimal("0.3"))


def test_agent_inventory_keeps_agents_with_nothing_to_join(connection: Connection) -> None:
    """Verifies an agent without version or runs is listed with empties, instead of vanishing."""
    agent_id = insert_agent(connection)

    with database_session(connection) as session:
        item = next(a for a in list_agent_inventory(session) if a.id == agent_id)

    assert (item.active_version_number, item.model_id, item.tool_names) == (None, None, [])
    assert (item.total_runs, item.total_cost) == (0, Decimal(0))


def test_agent_inventory_keeps_an_agent_whose_model_no_longer_exists(
    connection: Connection,
) -> None:
    """Verifies a rollback to a missing model shows no model, instead of hiding the agent."""
    agent_id, _ = _insert_configured_agent(connection, uuid4())

    with database_session(connection) as session:
        item = next(a for a in list_agent_inventory(session) if a.id == agent_id)

    assert (item.active_version_number, item.model_id) == (1, None)


def test_model_inventory_counts_agents_and_adds_up_the_steps(connection: Connection) -> None:
    """Verifies adoption ignores archived agents and consumption comes from every step."""
    model_id = insert_model(connection)
    unused_id = insert_model(connection)
    first_agent, first_version = _insert_configured_agent(connection, model_id)
    second_agent, second_version = _insert_configured_agent(connection, model_id)
    archived_agent, archived_version = _insert_configured_agent(connection, model_id)
    connection.execute(
        update(_AGENTS).where(_AGENTS.c.id == archived_agent).values(status=AgentStatus.ARCHIVED)
    )
    _insert_run_with_step(connection, first_agent, first_version, model_id)
    _insert_run_with_step(connection, second_agent, second_version, model_id)
    _insert_run_with_step(connection, archived_agent, archived_version, model_id)

    with database_session(connection) as session:
        items = {item.id: item for item in list_model_inventory(session)}

    used = items[model_id]
    assert used.agents_using == 2
    assert (used.input_tokens, used.output_tokens, used.total_cost) == (30, 15, Decimal("0.3"))
    assert items[unused_id].agents_using == 0
    assert (items[unused_id].input_tokens, items[unused_id].total_cost) == (0, Decimal(0))


def test_summary_only_counts_the_cost_of_the_current_month(connection: Connection) -> None:
    """Verifies an older run stays out of the month's cost while the agents still count."""
    model_id = insert_model(connection)
    agent_id, version_id = _insert_configured_agent(connection, model_id)
    insert_finished_run(connection, agent_id, version_id, RunStatus.SUCCEEDED, 5, Decimal("0.4"))
    connection.execute(update(_RUNS).values(started_at="2020-01-15T00:00:00Z"))
    insert_finished_run(connection, agent_id, version_id, RunStatus.SUCCEEDED, 5, Decimal("0.1"))

    with database_session(connection) as session:
        summary = get_inventory_summary(session)

    assert summary.cost_current_month == Decimal("0.1")
    assert summary.agents_by_status[AgentStatus.DRAFT] >= 1
    assert model_id in {model.id for model in summary.models_in_use}


def test_orchestration_inventory_groups_ordered_steps_with_their_models(
    connection: Connection,
) -> None:
    """Verifies each flow gets only its steps, in order, with the current model and tools."""
    model_id = insert_model(connection)
    first_agent, _ = _insert_configured_agent(connection, model_id, ["consultar_factura"])
    second_agent, _ = _insert_configured_agent(connection, model_id)
    flow = Flow(
        orchestration_id=uuid4(),
        name="Flujo",
        description="Prueba",
        orchestration_type=OrchestrationType.SEQUENTIAL,
        steps=(FlowStep(first_agent, "a", "b"), FlowStep(second_agent, "b", "c")),
    )
    other = Flow(uuid4(), "Otro", "Prueba", OrchestrationType.SINGLE_AGENT, ())

    with database_session(connection) as session:
        save_flow(session, flow)
        save_flow(session, other)
        items = {item.id: item for item in list_orchestration_inventory(session)}

    steps = items[flow.orchestration_id].steps
    assert [step.agent_id for step in steps] == [first_agent, second_agent]
    assert [step.step_order for step in steps] == [1, 2]
    assert steps[0].tool_names == ["consultar_factura"]
    assert steps[1].model_name == "Test model"
    assert items[other.orchestration_id].steps == []


def _agent(status: AgentStatus, kind: AgentKind) -> AgentInventoryItem:
    """Builds an agent row where only the status and the kind matter.

    Args:
        status: The status of the agent.
        kind: The kind of the agent.

    Returns:
        AgentInventoryItem: the row.
    """
    return AgentInventoryItem(
        id=uuid4(),
        name="Agente",
        owner_area="Área",
        kind=kind,
        status=status,
        active_version_number=1,
        model_id=None,
        model_name=None,
        tool_names=[],
        knowledge_base_id=None,
        knowledge_base_name=None,
        total_runs=0,
        total_cost=Decimal(0),
    )


def _model(name: str, agents_using: int) -> ModelInventoryItem:
    """Builds a model row where only the name and the adoption matter.

    Args:
        name: The name of the model.
        agents_using: How many agents use it.

    Returns:
        ModelInventoryItem: the row.
    """
    return ModelInventoryItem(
        id=uuid4(),
        name=name,
        provider=ProviderName.OPENAI,
        size=ModelSize.SMALL,
        is_active=True,
        agents_using=agents_using,
        input_tokens=0,
        output_tokens=0,
        total_cost=Decimal(0),
    )


def test_build_summary_counts_every_status_and_keeps_only_models_in_use() -> None:
    """Verifies absent statuses read zero and a model nobody uses is not presented as in use."""
    agents = [
        _agent(AgentStatus.PUBLISHED, AgentKind.SYSTEM),
        _agent(AgentStatus.PUBLISHED, AgentKind.USER),
        _agent(AgentStatus.DRAFT, AgentKind.USER),
    ]

    summary = build_summary(agents, [_model("Luna", 3), _model("Sol", 0)], Decimal("1.5"))

    assert (summary.total_agents, summary.system_agents) == (3, 1)
    assert summary.agents_by_status == {
        AgentStatus.DRAFT: 1,
        AgentStatus.TESTING: 0,
        AgentStatus.PUBLISHED: 2,
        AgentStatus.ARCHIVED: 0,
    }
    assert summary.cost_current_month == Decimal("1.5")
    assert [model.name for model in summary.models_in_use] == ["Luna"]
