import pytest

from bia.providers.artifacts import ProviderName
from bia.providers.base import UnknownProviderError
from bia.providers.factory import get_provider
from bia.providers.openai.provider import OpenAIModelProvider


def test_get_provider_resolves_the_text_stored_in_the_catalog() -> None:
    """Verifies a catalog row's plain text reaches the right implementation."""
    assert isinstance(get_provider("openai"), OpenAIModelProvider)


@pytest.mark.parametrize("provider_name", list(ProviderName))
def test_every_declared_provider_has_an_implementation(provider_name: ProviderName) -> None:
    """Verifies adding an enum member without registering its builder is caught."""
    assert get_provider(provider_name) is get_provider(provider_name)


def test_get_provider_names_the_rejected_value_and_the_options() -> None:
    """Verifies an unknown provider fails saying what was asked and what is valid."""
    with pytest.raises(UnknownProviderError, match="'anthropic'.*Supported providers: openai"):
        get_provider("anthropic")
