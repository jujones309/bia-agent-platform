import logging
import time
from collections.abc import Callable

from openai import OpenAI, OpenAIError
from pydantic import BaseModel, ValidationError

from bia.providers.artifacts import (
    ChatMessage,
    ChatResult,
    EmbeddingResult,
    StructuredChatResult,
    ToolDefinition,
)
from bia.providers.base import ModelProvider, ProviderError
from bia.providers.openai.config import OpenAIProviderConfig
from bia.providers.openai.mapping import (
    ensure_usable_response,
    to_chat_message,
    to_embedding_usage,
    to_response_usage,
    to_wire_items,
    to_wire_tool,
)
from bia.settings.config import get_settings

logger = logging.getLogger(__name__)

_MILLISECONDS_PER_SECOND = 1000


def _timed_request[ResponseT](request: Callable[[], ResponseT]) -> tuple[ResponseT, int]:
    """Runs an API request, measuring it and translating its failures.

    Exists so every call measures latency the same way and no SDK exception leaves this
    vertical; used by all the methods of `OpenAIModelProvider`. The latency includes the
    SDK's retries, because that is what the caller waited.

    Args:
        request: The API call to run.

    Returns:
        tuple[ResponseT, int]: the API response and the latency in milliseconds.

    Raises:
        ProviderError: If the call fails or its answer does not validate.
    """
    started_at = time.perf_counter()
    try:
        response = request()
    except (OpenAIError, ValidationError) as error:
        raise ProviderError(f"OpenAI request failed: {error}") from error
    elapsed_seconds = time.perf_counter() - started_at
    return response, round(elapsed_seconds * _MILLISECONDS_PER_SECOND)


def _to_wire_input(messages: list[ChatMessage]) -> list[dict[str, object]]:
    """Converts a conversation to the input of the Responses API.

    Exists because one message can become several items; used by `OpenAIModelProvider`.

    Args:
        messages: The conversation so far.

    Returns:
        list[dict[str, object]]: the items of every message, in order.
    """
    return [item for message in messages for item in to_wire_items(message)]


class OpenAIModelProvider(ModelProvider):
    """Implements the `ModelProvider` contract on top of OpenAI's API.

    Exists as the only place of the platform that talks to OpenAI; obtained through
    `get_provider` by the verticals that need an LLM. Uses the Responses API because the
    catalog's models do not accept function tools on Chat Completions. Every call sends
    `store=False`: the conversation is replayed in full on each turn, so OpenAI does not
    need to keep customer data.
    """

    def __init__(self, client: OpenAI) -> None:
        """Stores the client used for every call.

        Args:
            client (OpenAI): The configured SDK client.
        """
        self._client = client

    def chat(
        self,
        messages: list[ChatMessage],
        model: str,
        tools: list[ToolDefinition] | None = None,
    ) -> ChatResult:
        """Sends a conversation to a model and returns its next message.

        Exists to implement the contract's chat. Tools are sent only when given, so an
        agent without tools sends no empty list.

        Args:
            messages: The conversation so far.
            model: The catalog's `provider_model_id` of the model to call.
            tools: The tools the model may request, if any.

        Returns:
            ChatResult: the model's message, with its usage and latency.

        Raises:
            ProviderError: If the call fails or the response is truncated, refused or empty.
        """
        optional_parameters = {"tools": [to_wire_tool(tool) for tool in tools]} if tools else {}
        response, latency_ms = _timed_request(
            lambda: self._client.responses.create(
                model=model,
                input=_to_wire_input(messages),
                store=False,
                **optional_parameters,
            )
        )
        ensure_usable_response(response)
        logger.info("OpenAI chat with %s finished in %d ms", model, latency_ms)
        return ChatResult(
            message=to_chat_message(response),
            usage=to_response_usage(response.usage),
            latency_ms=latency_ms,
        )

    def chat_structured[ResponseT: BaseModel](
        self,
        messages: list[ChatMessage],
        response_model: type[ResponseT],
        model: str,
    ) -> StructuredChatResult[ResponseT]:
        """Sends a conversation to a model that must answer with structured data.

        Exists to implement the contract's structured output with the SDK's parsing, which
        derives the schema from the pydantic model and validates the answer against it.

        Args:
            messages: The conversation so far.
            response_model: The pydantic model the answer must validate against.
            model: The catalog's `provider_model_id` of the model to call.

        Returns:
            StructuredChatResult[ResponseT]: the validated instance, with usage and latency.

        Raises:
            ProviderError: If the call fails, the model refuses or the answer is invalid.
        """
        response, latency_ms = _timed_request(
            lambda: self._client.responses.parse(
                model=model,
                input=_to_wire_input(messages),
                text_format=response_model,
                store=False,
            )
        )
        ensure_usable_response(response)
        if response.output_parsed is None:
            raise ProviderError(f"OpenAI returned no {response_model.__name__} instance")
        logger.info("OpenAI structured chat with %s finished in %d ms", model, latency_ms)
        return StructuredChatResult[response_model](
            parsed=response.output_parsed,
            usage=to_response_usage(response.usage),
            latency_ms=latency_ms,
        )

    def embed(self, texts: list[str], model: str) -> EmbeddingResult:
        """Generates the embeddings of a batch of texts in one call.

        Exists to implement the contract's embeddings. Sorts by the returned index because
        each vector must stay aligned with its text.

        Args:
            texts: The texts to embed; must not be empty.
            model: The catalog's `provider_model_id` of the embedding model.

        Returns:
            EmbeddingResult: one vector per text in input order, with usage and latency.

        Raises:
            ValueError: If `texts` is empty.
            ProviderError: If the call fails or returns a different number of vectors.
        """
        if not texts:
            raise ValueError("Cannot embed an empty list of texts")

        response, latency_ms = _timed_request(
            lambda: self._client.embeddings.create(model=model, input=texts)
        )
        if len(response.data) != len(texts):
            raise ProviderError(
                f"OpenAI returned {len(response.data)} embeddings for {len(texts)} texts"
            )
        logger.info("OpenAI embedded %d texts with %s in %d ms", len(texts), model, latency_ms)
        ordered = sorted(response.data, key=lambda item: item.index)
        return EmbeddingResult(
            embeddings=[item.embedding for item in ordered],
            usage=to_embedding_usage(response.usage),
            latency_ms=latency_ms,
        )


def build_openai_provider() -> OpenAIModelProvider:
    """Builds the provider from the platform's settings.

    Exists to keep the client's construction next to its implementation; registered in
    `bia/providers/factory.py`.

    Returns:
        OpenAIModelProvider: a provider with a configured client.
    """
    config = OpenAIProviderConfig()
    client = OpenAI(
        api_key=get_settings().openai_api_key.get_secret_value(),
        timeout=config.timeout_seconds,
        max_retries=config.max_retries,
    )
    return OpenAIModelProvider(client)
