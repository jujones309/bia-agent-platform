from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from bia.catalog.models.artifacts import CatalogModel, ModelSize
from bia.providers.artifacts import ProviderName, TokenUsage
from bia.providers.cost import compute_cost


def _catalog_model(input_price: str, output_price: str) -> CatalogModel:
    """Builds a catalog entry with the given prices per million tokens.

    Args:
        input_price: USD per 1M input tokens.
        output_price: USD per 1M output tokens.

    Returns:
        CatalogModel: the entry to price calls with.
    """
    return CatalogModel(
        id=uuid4(),
        name="Test model",
        provider=ProviderName.OPENAI,
        provider_model_id="test-model",
        size=ModelSize.LARGE,
        input_cost_per_million=Decimal(input_price),
        output_cost_per_million=Decimal(output_price),
        context_window=1000,
        recommended_use="Tests",
        is_active=True,
        created_at=datetime.now(UTC),
    )


@pytest.mark.parametrize(
    ("input_tokens", "output_tokens", "expected"),
    [
        (1_000_000, 0, "2"),
        (0, 1_000_000, "10"),
        (1500, 300, "0.006"),
        (1, 1, "0.000012"),
        (0, 0, "0"),
    ],
)
def test_compute_cost_prices_input_and_output_at_their_own_rate(
    input_tokens: int, output_tokens: int, expected: str
) -> None:
    """Verifies the amount, which would change if the rates were swapped or misscaled."""
    usage = TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens)

    assert compute_cost(usage, _catalog_model("2.00", "10.00")) == Decimal(expected)


def test_compute_cost_of_an_embedding_only_charges_input() -> None:
    """Verifies an embedding model, priced at 0 for output, costs just its input tokens."""
    usage = TokenUsage(input_tokens=500, output_tokens=0)

    assert compute_cost(usage, _catalog_model("0.02", "0")) == Decimal("0.00001")


def test_compute_cost_does_not_accumulate_float_errors() -> None:
    """Verifies many small calls add up exactly, as the traces' totals require."""
    usage = TokenUsage(input_tokens=1, output_tokens=0)
    model = _catalog_model("0.10", "0")

    total = sum((compute_cost(usage, model) for _ in range(1000)), Decimal(0))

    assert total == Decimal("0.0001")
