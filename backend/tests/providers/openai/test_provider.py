import json

import httpx
import pytest
from openai import OpenAI
from pydantic import BaseModel

from bia.providers.artifacts import ChatMessage, MessageRole, ToolDefinition
from bia.providers.base import ProviderError
from bia.providers.openai.provider import OpenAIModelProvider

_MODEL = "catalog-model"
_USER_MESSAGE = ChatMessage(role=MessageRole.USER, content="Hola")
_TOOL = ToolDefinition(name="consultar_factura", description="Consulta", parameters_schema={})
_FUNCTION_CALL = {
    "type": "function_call",
    "id": "fc-1",
    "call_id": "call-1",
    "name": "consultar_factura",
    "arguments": '{"cliente": "1"}',
}
_REFUSAL = {
    "type": "message",
    "id": "msg-1",
    "role": "assistant",
    "status": "completed",
    "content": [{"type": "refusal", "refusal": "No puedo"}],
}


class _Verdict(BaseModel):
    """Stands in for a structured answer such as a judge's verdict."""

    label: str


class _ScriptedApi:
    """Answers the SDK's HTTP requests, so tests exercise the real client without network."""

    def __init__(self, status_code: int, body: dict[str, object]) -> None:
        """Stores the response to give.

        Args:
            status_code (int): The HTTP status of every response.
            body (dict[str, object]): The JSON body of every response.
        """
        self._status_code = status_code
        self._body = body
        self.request_bodies: list[dict[str, object]] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        """Records the request's body and returns the scripted response.

        Args:
            request: The request made by the SDK.

        Returns:
            httpx.Response: the scripted response.
        """
        self.request_bodies.append(json.loads(request.content))
        return httpx.Response(self._status_code, json=self._body)

    def provider(self) -> OpenAIModelProvider:
        """Builds a provider whose SDK client talks to this scripted API.

        Returns:
            OpenAIModelProvider: the provider under test.
        """
        http_client = httpx.Client(transport=httpx.MockTransport(self.handle))
        client = OpenAI(api_key="test-key", http_client=http_client, max_retries=0)
        return OpenAIModelProvider(client)


def _text_output(text: str) -> dict[str, object]:
    """Builds an output item holding text.

    Args:
        text: The text of the item.

    Returns:
        dict[str, object]: the output item.
    """
    return {
        "type": "message",
        "id": "msg-1",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }


def _response(output: list[dict[str, object]], **overrides: object) -> dict[str, object]:
    """Builds the body of a Responses API response.

    Args:
        output: The output items.
        **overrides: Fields that replace the defaults of a completed response.

    Returns:
        dict[str, object]: the JSON body.
    """
    usage = {
        "input_tokens": 11,
        "output_tokens": 7,
        "total_tokens": 18,
        "input_tokens_details": {"cached_tokens": 0},
        "output_tokens_details": {"reasoning_tokens": 0},
    }
    return {
        "id": "response-1",
        "object": "response",
        "created_at": 1,
        "model": _MODEL,
        "status": "completed",
        "output": output,
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
        "usage": usage,
        **overrides,
    }


def test_chat_returns_the_text_and_the_usage() -> None:
    """Verifies the response is translated, without mixing input and output tokens."""
    api = _ScriptedApi(200, _response([_text_output("Hola, ¿en qué ayudo?")]))

    result = api.provider().chat([_USER_MESSAGE], _MODEL)

    assert result.message.role == MessageRole.ASSISTANT
    assert result.message.content == "Hola, ¿en qué ayudo?"
    assert result.message.tool_calls == []
    assert (result.usage.input_tokens, result.usage.output_tokens) == (11, 7)
    assert api.request_bodies[0]["model"] == _MODEL


def test_chat_returns_requested_tool_calls_with_raw_arguments() -> None:
    """Verifies the id is the one a tool result must reference, and arguments stay untouched."""
    api = _ScriptedApi(200, _response([_FUNCTION_CALL]))

    message = api.provider().chat([_USER_MESSAGE], _MODEL, tools=[_TOOL]).message

    assert message.content is None
    assert message.tool_calls[0].id == "call-1"
    assert message.tool_calls[0].name == "consultar_factura"
    assert message.tool_calls[0].arguments == '{"cliente": "1"}'
    assert api.request_bodies[0]["tools"][0]["name"] == "consultar_factura"


def test_chat_omits_tools_when_there_are_none() -> None:
    """Verifies an agent without tools sends no empty tool list."""
    api = _ScriptedApi(200, _response([_text_output("ok")]))

    api.provider().chat([_USER_MESSAGE], _MODEL, tools=[])

    assert "tools" not in api.request_bodies[0]


def test_calls_ask_openai_not_to_store_the_conversation() -> None:
    """Verifies customer conversations are not retained as responses on OpenAI's side."""
    api = _ScriptedApi(200, _response([_text_output('{"label": "exists"}')]))

    api.provider().chat([_USER_MESSAGE], _MODEL)
    api.provider().chat_structured([_USER_MESSAGE], _Verdict, _MODEL)

    assert [body["store"] for body in api.request_bodies] == [False, False]


def test_chat_rejects_an_incomplete_response() -> None:
    """Verifies a partial answer is not passed off as final, and the reason is stated."""
    body = _response(
        [_text_output("Tu saldo es")],
        status="incomplete",
        incomplete_details={"reason": "max_output_tokens"},
    )

    with pytest.raises(ProviderError, match="incomplete.*max_output_tokens"):
        _ScriptedApi(200, body).provider().chat([_USER_MESSAGE], _MODEL)


def test_chat_rejects_a_failed_response() -> None:
    """Verifies a failure reported inside a 200 response is not ignored."""
    body = _response(
        [], status="failed", error={"code": "server_error", "message": "Something broke"}
    )

    with pytest.raises(ProviderError, match="failed.*Something broke"):
        _ScriptedApi(200, body).provider().chat([_USER_MESSAGE], _MODEL)


def test_chat_rejects_a_refusal() -> None:
    """Verifies a refusal surfaces as an error stating the reason."""
    with pytest.raises(ProviderError, match="No puedo"):
        _ScriptedApi(200, _response([_REFUSAL])).provider().chat([_USER_MESSAGE], _MODEL)


def test_chat_rejects_an_empty_message() -> None:
    """Verifies output with neither text nor tools does not stall the loop silently."""
    with pytest.raises(ProviderError, match="empty message"):
        _ScriptedApi(200, _response([])).provider().chat([_USER_MESSAGE], _MODEL)


def test_chat_rejects_a_response_without_usage() -> None:
    """Verifies an untraceable call fails instead of being recorded as free."""
    body = _response([_text_output("ok")], usage=None)

    with pytest.raises(ProviderError, match="without usage"):
        _ScriptedApi(200, body).provider().chat([_USER_MESSAGE], _MODEL)


def test_api_errors_are_translated_so_no_sdk_exception_escapes() -> None:
    """Verifies consumers can handle failures without depending on the SDK."""
    api = _ScriptedApi(429, {"error": {"message": "Rate limit reached"}})

    with pytest.raises(ProviderError, match="Rate limit reached"):
        api.provider().chat([_USER_MESSAGE], _MODEL)


def test_chat_structured_returns_a_validated_instance_with_usage() -> None:
    """Verifies the typed answer arrives along with the data tracing needs."""
    api = _ScriptedApi(200, _response([_text_output('{"label": "exists"}')]))

    result = api.provider().chat_structured([_USER_MESSAGE], _Verdict, _MODEL)

    assert result.parsed == _Verdict(label="exists")
    assert result.usage.output_tokens == 7
    assert api.request_bodies[0]["text"]["format"]["name"] == "_Verdict"


def test_chat_structured_rejects_an_answer_that_does_not_validate() -> None:
    """Verifies data outside the schema never reaches a judge's consumer."""
    api = _ScriptedApi(200, _response([_text_output('{"other": 1}')]))

    with pytest.raises(ProviderError, match="request failed"):
        api.provider().chat_structured([_USER_MESSAGE], _Verdict, _MODEL)


def test_chat_structured_rejects_a_refusal() -> None:
    """Verifies a refusal fails with its reason instead of producing an empty verdict."""
    api = _ScriptedApi(200, _response([_REFUSAL]))

    with pytest.raises(ProviderError, match="No puedo"):
        api.provider().chat_structured([_USER_MESSAGE], _Verdict, _MODEL)


def _embedding_response(indexed_vectors: list[tuple[int, list[float]]]) -> dict[str, object]:
    """Builds the body of an embeddings response.

    Args:
        indexed_vectors: The input index and vector of each returned item, in response order.

    Returns:
        dict[str, object]: the JSON body.
    """
    return {
        "object": "list",
        "model": _MODEL,
        "data": [
            {"object": "embedding", "index": index, "embedding": vector}
            for index, vector in indexed_vectors
        ],
        "usage": {"prompt_tokens": 6, "total_tokens": 6},
    }


def test_embed_aligns_vectors_with_their_texts_even_if_returned_out_of_order() -> None:
    """Verifies a text is never stored with another text's vector."""
    api = _ScriptedApi(200, _embedding_response([(1, [0.2]), (0, [0.1])]))

    result = api.provider().embed(["primero", "segundo"], _MODEL)

    assert result.embeddings == [[0.1], [0.2]]
    assert (result.usage.input_tokens, result.usage.output_tokens) == (6, 0)


def test_embed_sends_the_whole_batch_in_one_request() -> None:
    """Verifies the batch is one call, which is what makes ingestion affordable."""
    api = _ScriptedApi(200, _embedding_response([(0, [0.1]), (1, [0.2])]))

    api.provider().embed(["primero", "segundo"], _MODEL)

    assert len(api.request_bodies) == 1
    assert api.request_bodies[0]["input"] == ["primero", "segundo"]


def test_embed_rejects_an_empty_batch_without_calling_the_api() -> None:
    """Verifies the mistake fails locally with a clear message."""
    api = _ScriptedApi(200, _embedding_response([]))

    with pytest.raises(ValueError, match="empty list"):
        api.provider().embed([], _MODEL)
    assert api.request_bodies == []


def test_embed_rejects_a_response_with_missing_vectors() -> None:
    """Verifies a partial response cannot misalign texts and vectors."""
    api = _ScriptedApi(200, _embedding_response([(0, [0.1])]))

    with pytest.raises(ProviderError, match="1 embeddings for 2 texts"):
        api.provider().embed(["primero", "segundo"], _MODEL)
