import pytest
from pydantic import BaseModel

from bia.providers.artifacts import ChatMessage, MessageRole, ToolCall
from bia.providers.base import ProviderError
from tests.providers.fake import FakeModelProvider

_MODEL = "fake-model"
_QUESTION = ChatMessage(role=MessageRole.USER, content="¿Cuál es mi saldo?")


class _Verdict(BaseModel):
    """Stands in for a structured answer such as a judge's verdict."""

    label: str


class _OtherAnswer(BaseModel):
    """Stands in for a structured answer of a type the caller did not ask for."""

    value: int


def test_chat_replays_a_tool_request_and_then_the_final_answer_in_order() -> None:
    """Verifies the fake can drive the two turns of a tool-calling loop."""
    provider = FakeModelProvider()
    tool_call = ToolCall(id="call-1", name="consultar_factura", arguments='{"cliente": "1"}')
    provider.queue_tool_calls([tool_call])
    provider.queue_text("Tu saldo es 100")

    first = provider.chat([_QUESTION], _MODEL)
    second = provider.chat([_QUESTION, first.message], _MODEL)

    assert first.message.tool_calls == [tool_call]
    assert first.message.content is None
    assert second.message.content == "Tu saldo es 100"
    assert second.message.tool_calls == []
    assert provider.chat_requests[1] == [_QUESTION, first.message]


def test_chat_without_a_scripted_answer_fails_the_test() -> None:
    """Verifies an unexpected extra call is exposed and not answered with invented data."""
    with pytest.raises(AssertionError, match="no scripted answer"):
        FakeModelProvider().chat([_QUESTION], _MODEL)


def test_chat_raises_a_scripted_error_and_then_continues() -> None:
    """Verifies provider failures can be simulated at a specific turn."""
    provider = FakeModelProvider()
    provider.queue_chat_error(ProviderError("rate limited"))
    provider.queue_text("ok")

    with pytest.raises(ProviderError, match="rate limited"):
        provider.chat([_QUESTION], _MODEL)
    assert provider.chat([_QUESTION], _MODEL).message.content == "ok"


def test_chat_structured_returns_the_scripted_instance() -> None:
    """Verifies judges can be simulated with a typed answer."""
    provider = FakeModelProvider()
    provider.queue_structured(_Verdict(label="exists"))

    result = provider.chat_structured([_QUESTION], _Verdict, _MODEL)

    assert result.parsed == _Verdict(label="exists")


def test_chat_structured_rejects_an_instance_of_another_type() -> None:
    """Verifies a badly scripted test fails, since a real provider could not answer that."""
    provider = FakeModelProvider()
    provider.queue_structured(_OtherAnswer(value=1))

    with pytest.raises(TypeError, match="_OtherAnswer, not _Verdict"):
        provider.chat_structured([_QUESTION], _Verdict, _MODEL)


def test_embed_is_deterministic_and_distinguishes_texts() -> None:
    """Verifies vectors behave enough like real ones for similarity-based code to be tested."""
    provider = FakeModelProvider(embedding_dimensions=4)

    first, same, other = provider.embed(["factura", "factura", "tarifa"], _MODEL).embeddings

    assert first == same
    assert first != other
    assert len(first) == 4


def test_embed_rejects_an_empty_batch_like_the_real_provider() -> None:
    """Verifies the fake does not accept what production would reject."""
    with pytest.raises(ValueError, match="empty list"):
        FakeModelProvider().embed([], _MODEL)
