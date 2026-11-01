from collections import Counter, defaultdict
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from bia.agents.artifacts import AgentKind, AgentStatus
from bia.database.queries import DatabaseTable, SqlOperation, load_sql
from bia.inventory.artifacts import (
    AgentInventoryItem,
    InventorySummary,
    ModelInventoryItem,
    OrchestrationInventoryItem,
    OrchestrationStepInventoryItem,
)


def list_agent_inventory(session: Session) -> list[AgentInventoryItem]:
    """Lists every agent with its area, model, tools, knowledge base, status, runs and cost.

    Exists so one call answers which agents exist and what they cost; used by the inventory API
    and by `get_inventory_summary`.

    Args:
        session: The open session to read through.

    Returns:
        list[AgentInventoryItem]: every agent, also system and archived ones, newest first.
    """
    rows = session.execute(text(load_sql(DatabaseTable.AGENTS, SqlOperation.INVENTORY))).mappings()
    return [AgentInventoryItem.model_validate(dict(row)) for row in rows]


def list_model_inventory(session: Session) -> list[ModelInventoryItem]:
    """Lists every catalog model with how many agents use it, its tokens and its total cost.

    Exists so one call answers which models the company depends on; used by the inventory API and
    by `get_inventory_summary`.

    Args:
        session: The open session to read through.

    Returns:
        list[ModelInventoryItem]: every model, also retired or unused ones, ordered by name.
    """
    sql = load_sql(DatabaseTable.MODELS, SqlOperation.INVENTORY)
    rows = session.execute(text(sql), {"archived_status": AgentStatus.ARCHIVED}).mappings()
    return [ModelInventoryItem.model_validate(dict(row)) for row in rows]


def _list_steps_by_flow(session: Session) -> dict[UUID, list[OrchestrationStepInventoryItem]]:
    """Lists the steps of every flow, grouped by flow and in execution order.

    Exists to assemble the flows with one query per table; used by
    `list_orchestration_inventory`.

    Args:
        session: The open session to read through.

    Returns:
        dict[UUID, list[OrchestrationStepInventoryItem]]: the steps of each flow that has any.
    """
    sql = load_sql(DatabaseTable.ORCHESTRATION_STEPS, SqlOperation.INVENTORY)
    steps_by_flow: dict[UUID, list[OrchestrationStepInventoryItem]] = defaultdict(list)
    for row in session.execute(text(sql)).mappings():
        step = OrchestrationStepInventoryItem.model_validate(dict(row))
        steps_by_flow[step.orchestration_id].append(step)
    return dict(steps_by_flow)


def list_orchestration_inventory(session: Session) -> list[OrchestrationInventoryItem]:
    """Lists every registered flow with its steps, agents and models.

    Exists so one call shows how agents combine; used by the inventory API.

    Args:
        session: The open session to read through.

    Returns:
        list[OrchestrationInventoryItem]: every flow, ordered by name.
    """
    steps_by_flow = _list_steps_by_flow(session)
    sql = load_sql(DatabaseTable.ORCHESTRATIONS, SqlOperation.LIST)
    return [
        OrchestrationInventoryItem.model_validate(
            {**row, "steps": steps_by_flow.get(row["id"], [])}
        )
        for row in session.execute(text(sql)).mappings()
    ]


def build_summary(
    agents: list[AgentInventoryItem],
    models: list[ModelInventoryItem],
    cost_current_month: Decimal,
) -> InventorySummary:
    """Reduces the inventories to the numbers of the global view.

    Exists apart from the reads so the counting rules do not depend on a database; used by
    `get_inventory_summary`.

    Args:
        agents: The whole agent inventory.
        models: The whole model inventory.
        cost_current_month: The cost of the runs started this month.

    Returns:
        InventorySummary: the totals, with every status present even at zero.
    """
    statuses = Counter(agent.status for agent in agents)
    return InventorySummary(
        total_agents=len(agents),
        system_agents=sum(agent.kind is AgentKind.SYSTEM for agent in agents),
        agents_by_status={status: statuses[status] for status in AgentStatus},
        cost_current_month=cost_current_month,
        models_in_use=[model for model in models if model.agents_using > 0],
    )


def get_inventory_summary(session: Session) -> InventorySummary:
    """Computes the agents by status, the cost of the month and the models in use.

    Exists as the global view of the platform; used by the inventory API. It derives from the other
    inventories so the three views cannot disagree on what counts.

    Args:
        session: The open session to read through.

    Returns:
        InventorySummary: the current numbers of the platform.
    """
    sql = load_sql(DatabaseTable.RUNS, SqlOperation.COST_OF_CURRENT_MONTH)
    cost_current_month = session.execute(text(sql)).scalar_one()
    return build_summary(
        list_agent_inventory(session), list_model_inventory(session), cost_current_month
    )
