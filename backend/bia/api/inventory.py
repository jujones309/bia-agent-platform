from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from bia.api.dependencies import get_session
from bia.inventory.artifacts import (
    AgentInventoryItem,
    InventorySummary,
    ModelInventoryItem,
    OrchestrationInventoryItem,
)
from bia.inventory.repository import (
    get_inventory_summary,
    list_agent_inventory,
    list_model_inventory,
    list_orchestration_inventory,
)

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("/agents", response_model=list[AgentInventoryItem])
def get_agents(session: Annotated[Session, Depends(get_session)]) -> list[AgentInventoryItem]:
    """Lists every agent with its configuration and accumulated cost.

    Exists as the overview of the agents of Bia; served as `GET /inventory/agents`.

    Args:
        session: The session of the request.

    Returns:
        list[AgentInventoryItem]: every agent, newest first.
    """
    return list_agent_inventory(session)


@router.get("/models", response_model=list[ModelInventoryItem])
def get_models(session: Annotated[Session, Depends(get_session)]) -> list[ModelInventoryItem]:
    """Lists every catalog model with its adoption and consumption.

    Exists as the overview of the models Bia depends on; served as `GET /inventory/models`.

    Args:
        session: The session of the request.

    Returns:
        list[ModelInventoryItem]: every model, ordered by name.
    """
    return list_model_inventory(session)


@router.get("/orchestrations", response_model=list[OrchestrationInventoryItem])
def get_orchestrations(
    session: Annotated[Session, Depends(get_session)],
) -> list[OrchestrationInventoryItem]:
    """Lists every registered flow with its steps, agents and models.

    Exists as the overview of how agents combine; served as `GET /inventory/orchestrations`.

    Args:
        session: The session of the request.

    Returns:
        list[OrchestrationInventoryItem]: every flow, ordered by name.
    """
    return list_orchestration_inventory(session)


@router.get("/summary", response_model=InventorySummary)
def get_summary(session: Annotated[Session, Depends(get_session)]) -> InventorySummary:
    """Retrieves the global numbers of the platform.

    Exists as the one-glance view of the platform; served as `GET /inventory/summary`.

    Args:
        session: The session of the request.

    Returns:
        InventorySummary: the agents by status, the cost of the month and the models in use.
    """
    return get_inventory_summary(session)
