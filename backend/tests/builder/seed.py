from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from bia.agents.artifacts import AgentSpec, AgentVersion
from bia.catalog.models.artifacts import CatalogModel, ModelSize
from bia.providers.artifacts import ProviderName
from bia.runtime.execution import AgentExecution


def build_model(size: ModelSize = ModelSize.SMALL) -> CatalogModel:
    """Builds a catalog model priced at 1 and 2 USD per 1M tokens.

    Args:
        size: The size of the model.

    Returns:
        CatalogModel: the model.
    """
    return CatalogModel(
        id=uuid4(),
        name="Model",
        provider=ProviderName.OPENAI,
        provider_model_id="catalog-model",
        size=size,
        input_cost_per_million=Decimal(1),
        output_cost_per_million=Decimal(2),
        context_window=1000,
        recommended_use="Tests",
        is_active=True,
        created_at=datetime.now(UTC),
    )


def build_execution() -> AgentExecution:
    """Builds the execution of a system agent, whose prompt is recognizable in the requests.

    Returns:
        AgentExecution: the execution, without tools.
    """
    model = build_model()
    spec = AgentSpec(purpose="Sistema", system_prompt="Prompt versionado", model_id=model.id)
    version = AgentVersion(
        id=uuid4(),
        agent_id=uuid4(),
        version_number=1,
        spec=spec,
        designer_justification=None,
        created_at=datetime.now(UTC),
    )
    return AgentExecution(version, model, [])
