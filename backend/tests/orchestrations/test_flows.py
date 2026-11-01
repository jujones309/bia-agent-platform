from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import Connection, Engine

from bia.agents.repository import AgentNotFoundError
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
    register_billing_flow,
    sync_builder_flow,
)
from bia.orchestrations.repository import save_flow
from tests.tracing.seed import insert_agent


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
