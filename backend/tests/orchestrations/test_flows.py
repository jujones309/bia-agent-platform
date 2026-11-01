from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, Engine, Uuid, column, select, table

from bia.agents.artifacts import Agent
from bia.agents.repository import AgentNotFoundError, get_agent
from bia.builder.system_agents import (
    CASE_GENERATOR_AGENT_ID,
    DESIGNER_AGENT_ID,
    DUPLICATE_JUDGE_AGENT_ID,
    EVAL_JUDGE_AGENT_ID,
    sync_system_agents,
)
from bia.database.connection import database_session
from bia.database.migrate import apply_schema, apply_seeds
from bia.inventory.repository import list_orchestration_inventory
from bia.orchestrations.artifacts import Flow, FlowStep, OrchestrationType
from bia.orchestrations.flows import (
    BILLING_FLOW_ID,
    BUILDER_FLOW_ID,
    ProtectedFlowError,
    register_billing_flow,
    register_single_agent_flow,
    rename_single_agent_flow,
    retire_registered_flow,
    sync_builder_flow,
)
from bia.orchestrations.repository import OrchestrationNotFoundError, save_flow
from tests.tracing.seed import insert_agent

_ORCHESTRATIONS = table("orchestrations", column("id", Uuid), column("retired_at"))
_STEPS = table("orchestration_steps", column("orchestration_id", Uuid), column("agent_id", Uuid))


@pytest.fixture
def connection(integration_engine: Engine) -> Iterator[Connection]:
    """Provides a connection with the schema, the catalog and the system agents, rolled back later.

    Args:
        integration_engine: The engine of the real database.

    Returns:
        Iterator[Connection]: yields the connection inside the open transaction.
    """
    with integration_engine.connect() as open_connection:
        transaction = open_connection.begin()
        with database_session(open_connection) as session:
            apply_schema(session)
            apply_seeds(session)
            sync_system_agents(session)
        yield open_connection
        transaction.rollback()


def test_builder_flow_runs_the_four_system_agents_in_order_after_any_number_of_syncs(
    connection: Connection,
) -> None:
    """Verifies every startup leaves one flow in the agreed order, with models resolved."""
    with database_session(connection) as session:
        sync_builder_flow(session)
        sync_builder_flow(session)
        flows = {flow.id: flow for flow in list_orchestration_inventory(session)}

    flow = flows[BUILDER_FLOW_ID]
    assert flow.orchestration_type is OrchestrationType.SEQUENTIAL
    assert [step.agent_id for step in flow.steps] == [
        DUPLICATE_JUDGE_AGENT_ID,
        DESIGNER_AGENT_ID,
        CASE_GENERATOR_AGENT_ID,
        EVAL_JUDGE_AGENT_ID,
    ]
    assert all(step.model_name for step in flow.steps)


def test_billing_flow_points_to_the_given_agent_and_can_move_to_another(
    connection: Connection,
) -> None:
    """Verifies registering again replaces the agent, so a rebuilt assistant leaves no old step."""
    first_agent = insert_agent(connection)
    second_agent = insert_agent(connection)

    with database_session(connection) as session:
        register_billing_flow(session, first_agent)
        register_billing_flow(session, second_agent)
        flows = {flow.id: flow for flow in list_orchestration_inventory(session)}

    flow = flows[BILLING_FLOW_ID]
    assert flow.orchestration_type is OrchestrationType.SINGLE_AGENT
    assert [step.agent_id for step in flow.steps] == [second_agent]


def test_billing_flow_rejects_an_unknown_agent(connection: Connection) -> None:
    """Verifies a mistyped identifier names the agent instead of failing on a foreign key."""
    missing_id = uuid4()

    with (
        database_session(connection) as session,
        pytest.raises(AgentNotFoundError, match=str(missing_id)),
    ):
        register_billing_flow(session, missing_id)


def test_saving_a_shorter_definition_drops_the_leftover_steps(connection: Connection) -> None:
    """Verifies a flow that loses a step does not keep showing it."""
    agent_id = insert_agent(connection)
    long_flow = Flow(
        uuid4(),
        "Flujo",
        "Prueba",
        OrchestrationType.SEQUENTIAL,
        (FlowStep(agent_id, "a", "b"), FlowStep(agent_id, "b", "c")),
    )
    short_flow = Flow(
        long_flow.orchestration_id,
        "Flujo nuevo",
        "Prueba",
        OrchestrationType.SINGLE_AGENT,
        (FlowStep(agent_id, "a", "c"),),
    )

    with database_session(connection) as session:
        save_flow(session, long_flow)
        save_flow(session, short_flow)
        flows = {flow.id: flow for flow in list_orchestration_inventory(session)}

    flow = flows[long_flow.orchestration_id]
    assert (flow.name, len(flow.steps)) == ("Flujo nuevo", 1)
    assert flow.steps[0].delivers_output == "c"


def _flow_ids(connection: Connection) -> set[UUID]:
    """Lists the flows of the inventory.

    Args:
        connection: The connection of the test's transaction.

    Returns:
        set[UUID]: the identifiers of the flows in force.
    """
    with database_session(connection) as session:
        return {flow.id for flow in list_orchestration_inventory(session)}


def _agent(connection: Connection, agent_id: UUID) -> Agent:
    """Reads an agent of the registry.

    Args:
        connection: The connection of the test's transaction.
        agent_id: The agent to read.

    Returns:
        Agent: the agent.
    """
    with database_session(connection) as session:
        return get_agent(session, agent_id)


def test_a_published_agent_gets_one_flow_of_its_own_however_many_times_it_is_published(
    connection: Connection,
) -> None:
    """Verifies the flow carries the agent's identity and republishing does not pile up flows."""
    agent = _agent(connection, insert_agent(connection))
    flows_before = _flow_ids(connection)

    with database_session(connection) as session:
        register_single_agent_flow(session, agent)
        register_single_agent_flow(session, agent)
        flows = list_orchestration_inventory(session)

    new_flows = [flow for flow in flows if flow.id not in flows_before]
    assert len(new_flows) == 1
    assert new_flows[0].name == agent.name
    assert new_flows[0].orchestration_type is OrchestrationType.SINGLE_AGENT
    assert not new_flows[0].is_system
    assert [step.agent_id for step in new_flows[0].steps] == [agent.id]


def test_an_agent_in_a_declared_flow_does_not_get_a_second_one(connection: Connection) -> None:
    """Verifies republishing the billing assistant does not duplicate the flow declared by hand."""
    agent_id = insert_agent(connection)

    with database_session(connection) as session:
        register_billing_flow(session, agent_id)
    flows_before = _flow_ids(connection)
    with database_session(connection) as session:
        register_single_agent_flow(session, get_agent(session, agent_id))

    assert _flow_ids(connection) == flows_before


def test_retiring_a_flow_hides_it_and_publishing_again_does_not_bring_it_back(
    connection: Connection,
) -> None:
    """Verifies a person's decision survives every later publication of the agent."""
    agent = _agent(connection, insert_agent(connection))
    flows_before = _flow_ids(connection)
    with database_session(connection) as session:
        register_single_agent_flow(session, agent)
    new_flow_id = (_flow_ids(connection) - flows_before).pop()

    with database_session(connection) as session:
        retire_registered_flow(session, new_flow_id)
    assert new_flow_id not in _flow_ids(connection)

    with database_session(connection) as session:
        register_single_agent_flow(session, agent)
    assert new_flow_id not in _flow_ids(connection)


def test_retiring_keeps_the_row_and_the_steps_as_history(connection: Connection) -> None:
    """Verifies retiring hides without deleting, so the audit record survives."""
    agent_id = insert_agent(connection)
    with database_session(connection) as session:
        register_billing_flow(session, agent_id)
        retire_registered_flow(session, BILLING_FLOW_ID)

    retired = connection.execute(
        select(_ORCHESTRATIONS.c.retired_at).where(_ORCHESTRATIONS.c.id == BILLING_FLOW_ID)
    ).scalar_one()
    steps = connection.execute(
        select(_STEPS.c.agent_id).where(_STEPS.c.orchestration_id == BILLING_FLOW_ID)
    ).all()
    assert retired is not None
    assert [step.agent_id for step in steps] == [agent_id]


def test_registering_a_retired_flow_by_hand_puts_it_back_in_force(connection: Connection) -> None:
    """Verifies the explicit command stays the way to restore a declared flow."""
    agent_id = insert_agent(connection)
    with database_session(connection) as session:
        register_billing_flow(session, agent_id)
        retire_registered_flow(session, BILLING_FLOW_ID)
        register_billing_flow(session, agent_id)

    assert BILLING_FLOW_ID in _flow_ids(connection)


def test_retiring_twice_or_an_unknown_flow_fails_clearly(connection: Connection) -> None:
    """Verifies a wrong identifier is told apart from a successful removal."""
    with database_session(connection) as session:
        register_billing_flow(session, insert_agent(connection))
        retire_registered_flow(session, BILLING_FLOW_ID)

    with (
        database_session(connection) as session,
        pytest.raises(OrchestrationNotFoundError, match=str(BILLING_FLOW_ID)),
    ):
        retire_registered_flow(session, BILLING_FLOW_ID)


def test_the_flow_of_the_platform_cannot_be_retired_and_is_marked(connection: Connection) -> None:
    """Verifies the builder's flow stays, since the next startup would register it again."""
    with database_session(connection) as session:
        sync_builder_flow(session)
        with pytest.raises(ProtectedFlowError):
            retire_registered_flow(session, BUILDER_FLOW_ID)
        flows = {flow.id: flow for flow in list_orchestration_inventory(session)}

    assert flows[BUILDER_FLOW_ID].is_system


def test_renaming_follows_the_agent_only_in_its_automatic_flow(connection: Connection) -> None:
    """Verifies an edited identity reaches the automatic flow and spares a declared one."""
    automatic = _agent(connection, insert_agent(connection))
    declared_id = insert_agent(connection)
    flows_before = _flow_ids(connection)
    renamed = automatic.model_copy(update={"name": "Nuevo", "description": "Nueva"})
    with database_session(connection) as session:
        register_single_agent_flow(session, automatic)
        register_billing_flow(session, declared_id)
        rename_single_agent_flow(session, renamed)
        rename_single_agent_flow(session, get_agent(session, declared_id))
        flows = {flow.id: flow for flow in list_orchestration_inventory(session)}

    new_id = (set(flows) - flows_before - {BILLING_FLOW_ID}).pop()
    assert (flows[new_id].name, flows[new_id].description) == ("Nuevo", "Nueva")
    assert flows[BILLING_FLOW_ID].name == "Asistente de facturación"
