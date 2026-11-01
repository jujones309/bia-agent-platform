from collections.abc import Callable
from functools import lru_cache

from bia.providers.artifacts import ProviderName
from bia.providers.base import ModelProvider, UnknownProviderError
from bia.providers.openai.provider import build_openai_provider

_PROVIDER_BUILDERS: dict[ProviderName, Callable[[], ModelProvider]] = {
    ProviderName.OPENAI: build_openai_provider,
}


@lru_cache
def _build_provider(provider_name: ProviderName) -> ModelProvider:
    """Builds a provider once per process.

    Exists so all consumers share one provider and its HTTP connections; used by
    `get_provider`.

    Args:
        provider_name: The provider to build.

    Returns:
        ModelProvider: the cached provider.
    """
    return _PROVIDER_BUILDERS[provider_name]()


def get_provider(provider_name: str) -> ModelProvider:
    """Retrieves the implementation of a provider from its name.

    Exists so consumers go from a catalog entry to a provider without importing any
    implementation. Accepts plain text because that is how the catalog stores the name.

    Args:
        provider_name: A `ProviderName` member or its text value.

    Returns:
        ModelProvider: the shared provider implementation.

    Raises:
        UnknownProviderError: If the name is not a supported provider.
    """
    if provider_name not in list(ProviderName):
        supported = ", ".join(ProviderName)
        raise UnknownProviderError(
            f"Unknown model provider '{provider_name}'. Supported providers: {supported}"
        )
    return _build_provider(ProviderName(provider_name))
