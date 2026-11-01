from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from bia.agents.artifacts import AgentKind, AgentStatus
from bia.catalog.models.artifacts import ModelSize
from bia.orchestrations.artifacts import OrchestrationType
from bia.providers.artifacts import ProviderName


class AgentInventoryItem(BaseModel):
    """Describes one agent for the overview of what exists in Bia.

    Exists as the contract of `GET /inventory/agents`, gathering the registry, the active spec and
    the traces in one row; produced by `list_agent_inventory`.
    """

    id: UUID
    name: str
    owner_area: str
    kind: AgentKind
    status: AgentStatus
    active_version_number: int | None  # None only for rows that were created by hand
    model_id: UUID | None  # None without an active version or if the spec's model does not exist
    model_name: str | None
    tool_names: list[str]
    knowledge_base_id: UUID | None
    knowledge_base_name: str | None
    total_runs: int  # of every origin, also evals and playground
    total_cost: Decimal


class ModelInventoryItem(BaseModel):
    """Describes one catalog model with its adoption and its consumption.

    Exists as the contract of `GET /inventory/models`; produced by `list_model_inventory`.
    """

    id: UUID
    name: str
    provider: ProviderName
    size: ModelSize
    is_active: bool
    agents_using: int  # non-archived agents whose active spec names the model
    input_tokens: int
    output_tokens: int
    total_cost: Decimal


class OrchestrationStepInventoryItem(BaseModel):
    """Describes one step of a flow, with what its agent executes today.

    Exists nested in `OrchestrationInventoryItem`; the model and tools come from the agent's active
    version, so they follow any later edit.
    """

    orchestration_id: UUID
    step_order: int
    agent_id: UUID
    agent_name: str
    agent_status: AgentStatus
    model_id: UUID | None  # None without an active version or if the spec's model does not exist
    model_name: str | None
    tool_names: list[str]
    receives_context: str
    delivers_output: str


class OrchestrationInventoryItem(BaseModel):
    """Describes one registered flow with its steps in execution order.

    Exists as the contract of `GET /inventory/orchestrations`; produced by
    `list_orchestration_inventory`.
    """

    id: UUID
    name: str
    description: str
    orchestration_type: OrchestrationType
    steps: list[OrchestrationStepInventoryItem]


class InventorySummary(BaseModel):
    """Summarizes the whole platform in one view.

    Exists as the contract of `GET /inventory/summary`; produced by `build_summary`.
    """

    total_agents: int
    system_agents: int  # already included in the total and in the statuses
    agents_by_status: dict[AgentStatus, int]  # every status appears, also those at zero
    cost_current_month: Decimal  # of the runs started this calendar month, in UTC
    models_in_use: list[ModelInventoryItem]  # those named by the spec of a non-archived agent
