from decimal import Decimal

from bia.catalog.models.artifacts import CatalogModel
from bia.providers.artifacts import TokenUsage

_TOKENS_PER_PRICE_UNIT = Decimal(1_000_000)


def compute_cost(usage: TokenUsage, catalog_model: CatalogModel) -> Decimal:
    """Computes the USD cost of a provider call from the catalog's prices.

    Exists so every trace prices tokens the same way; used wherever an LLM call is recorded.
    Uses `Decimal` so accumulated costs carry no rounding error. All input tokens are priced
    at the standard rate, so calls served from the provider's cache are slightly overestimated.

    Args:
        usage: The tokens the call consumed.
        catalog_model: The catalog entry of the model that served the call.

    Returns:
        Decimal: the exact cost of the call in USD.
    """
    input_cost = usage.input_tokens * catalog_model.input_cost_per_million
    output_cost = usage.output_tokens * catalog_model.output_cost_per_million
    return (input_cost + output_cost) / _TOKENS_PER_PRICE_UNIT
