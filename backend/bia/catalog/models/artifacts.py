from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel

from bia.providers.artifacts import ProviderName


class ModelSize(StrEnum):
    """The categories used to choose a model from the catalog.

    Exists to mirror the `size` check of the `models` table; consumed by the designer when
    it picks a model and by the inventories.
    """

    LARGE = "large"
    SMALL = "small"
    EMBEDDING = "embedding"


class CatalogModel(BaseModel):
    """Represents one entry of the curated model catalog.

    Exists as the contract of a row of the `models` table; consumed by `compute_cost` and,
    from phase 3 on, by the catalog repository, the designer and the runtime.
    """

    id: UUID
    name: str
    provider: ProviderName
    provider_model_id: str
    size: ModelSize
    input_cost_per_million: Decimal
    output_cost_per_million: Decimal
    context_window: int
    recommended_use: str
    is_active: bool
    created_at: datetime
