from decimal import Decimal
from unittest.mock import sentinel
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from bia.agents.artifacts import AgentKind, AgentStatus
from bia.api import inventory as inventory_router
from bia.api.dependencies import get_session
from bia.api.main import app
from bia.catalog.models.artifacts import ModelSize
from bia.inventory.artifacts import (
    AgentInventoryItem,
    InventorySummary,
    ModelInventoryItem,
    OrchestrationInventoryItem,
    OrchestrationStepInventoryItem,
)
from bia.orchestrations.artifacts import OrchestrationType
from bia.providers.artifacts import ProviderName


def test_agents_inventory_exposes_configuration_and_cost(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the body answers who owns the agent, what it uses and what it has cost."""
    item = AgentInventoryItem(
        id=uuid4(),
        name="Bia Facturación",
        owner_area="Servicio al cliente",
        kind=AgentKind.USER,
        status=AgentStatus.PUBLISHED,
        active_version_number=1,
        model_id=uuid4(),
        model_name="Luna",
        tool_names=["consultar_factura"],
        knowledge_base_id=None,
        knowledge_base_name=None,
        total_runs=7,
        total_cost=Decimal("0.25"),
    )
    app.dependency_overrides[get_session] = lambda: sentinel.session
    monkeypatch.setattr(inventory_router, "list_agent_inventory", lambda _session: [item])

    body = api_client.get("/inventory/agents").json()[0]

    assert (body["owner_area"], body["model_name"]) == ("Servicio al cliente", "Luna")
    assert (body["tool_names"], body["total_runs"]) == (["consultar_factura"], 7)
    assert float(body["total_cost"]) == 0.25


def test_orchestrations_inventory_keeps_the_steps_nested_in_their_flow(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies each flow carries its ordered steps with agent and model."""
    flow_id = uuid4()
    step = OrchestrationStepInventoryItem(
        orchestration_id=flow_id,
        step_order=1,
        agent_id=uuid4(),
        agent_name="Juez",
        agent_status=AgentStatus.PUBLISHED,
        model_id=uuid4(),
        model_name="Luna",
        tool_names=[],
        receives_context="La necesidad",
        delivers_output="El veredicto",
    )
    flow = OrchestrationInventoryItem(
        id=flow_id,
        name="Agent Builder",
        description="Crea agentes",
        orchestration_type=OrchestrationType.SEQUENTIAL,
        steps=[step],
    )
    app.dependency_overrides[get_session] = lambda: sentinel.session
    monkeypatch.setattr(inventory_router, "list_orchestration_inventory", lambda _session: [flow])

    body = api_client.get("/inventory/orchestrations").json()[0]

    assert body["orchestration_type"] == "sequential"
    assert [item["agent_name"] for item in body["steps"]] == ["Juez"]
    assert body["steps"][0]["model_name"] == "Luna"


def test_models_and_summary_expose_their_numbers(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies consumption reaches the models body and the statuses key the summary."""
    model = ModelInventoryItem(
        id=uuid4(),
        name="Luna",
        provider=ProviderName.OPENAI,
        size=ModelSize.SMALL,
        is_active=True,
        agents_using=2,
        input_tokens=100,
        output_tokens=50,
        total_cost=Decimal("0.5"),
    )
    summary = InventorySummary(
        total_agents=2,
        system_agents=1,
        agents_by_status={AgentStatus.PUBLISHED: 2},
        cost_current_month=Decimal("0.5"),
        models_in_use=[model],
    )
    app.dependency_overrides[get_session] = lambda: sentinel.session
    monkeypatch.setattr(inventory_router, "list_model_inventory", lambda _session: [model])
    monkeypatch.setattr(inventory_router, "get_inventory_summary", lambda _session: summary)

    models = api_client.get("/inventory/models").json()
    body = api_client.get("/inventory/summary").json()

    assert (models[0]["agents_using"], models[0]["input_tokens"]) == (2, 100)
    assert body["agents_by_status"] == {"published": 2}
    assert body["models_in_use"][0]["name"] == "Luna"


@pytest.mark.parametrize("path", ["agents", "models", "orchestrations", "summary"])
def test_inventories_require_credentials(path: str) -> None:
    """Verifies costs and configuration stay behind the shared password."""
    assert TestClient(app).get(f"/inventory/{path}").status_code == 401
