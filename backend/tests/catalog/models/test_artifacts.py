import pytest
from pydantic import ValidationError

from bia.catalog.models.artifacts import CatalogModel

_ROW = {
    "id": "6f1c7c1e-0d6b-4a57-9a53-0f6f3f0a1b2c",
    "name": "Test model",
    "provider": "openai",
    "provider_model_id": "test-model",
    "size": "small",
    "input_cost_per_million": "0.10",
    "output_cost_per_million": "0.50",
    "context_window": 1000,
    "recommended_use": "Tests",
    "is_active": True,
    "created_at": "2026-10-31T00:00:00Z",
}


def test_catalog_model_keeps_prices_exact() -> None:
    """Verifies a price read from a row is not degraded to a float."""
    assert str(CatalogModel.model_validate(_ROW).input_cost_per_million) == "0.10"


@pytest.mark.parametrize(("column", "value"), [("provider", "acme"), ("size", "huge")])
def test_catalog_model_rejects_values_outside_the_closed_sets(column: str, value: str) -> None:
    """Verifies a corrupt catalog row fails on load, not later inside an agent run."""
    with pytest.raises(ValidationError):
        CatalogModel.model_validate({**_ROW, column: value})
