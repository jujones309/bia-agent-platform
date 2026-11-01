from abc import ABC, abstractmethod

from pydantic import BaseModel

from bia.providers.artifacts import (
    ChatMessage,
    ChatResult,
    EmbeddingResult,
    StructuredChatResult,
    ToolDefinition,
)


class ProviderError(RuntimeError):
    """Signals that a provider call failed or returned an unusable response.

    Exists so consumers handle failures without depending on any provider's SDK. Raised by
    `ModelProvider` implementations and handled by the runtime, the builder and the evals.
    """


class UnknownProviderError(ProviderError):
    """Signals that a provider name is not one the platform supports.

    Exists to name the rejected value and the valid options. Raised by `get_provider`.
    """


class ModelProvider(ABC):
    """Defines the single door through which the platform talks to LLMs.

    Exists so no vertical depends on a specific provider; implemented under
    `bia/providers/<provider>/` and consumed by the runtime, the builder, RAG and the evals.
    Model identifiers always come from the model catalog.
    """

    @abstractmethod
    def chat(
        self,
        messages: list[ChatMessage],
        model: str,
        tools: list[ToolDefinition] | None = None,
    ) -> ChatResult:
        """Sends a conversation to a model and returns its next message.

        Exists as the step of the runtime's tool-calling loop.

        Args:
            messages: The conversation so far.
            model: The catalog's `provider_model_id` of the model to call.
            tools: The tools the model may request, if any.

        Returns:
            ChatResult: the model's message, with its usage and latency.

        Raises:
            ProviderError: If the call fails or the response is truncated, refused or empty.
        """

    @abstractmethod
    def chat_structured[ResponseT: BaseModel](
        self,
        messages: list[ChatMessage],
        response_model: type[ResponseT],
        model: str,
    ) -> StructuredChatResult[ResponseT]:
        """Sends a conversation to a model that must answer with structured data.

        Exists so judges and the designer receive validated objects and never parse free text.

        Args:
            messages: The conversation so far.
            response_model: The pydantic model the answer must validate against.
            model: The catalog's `provider_model_id` of the model to call.

        Returns:
            StructuredChatResult[ResponseT]: the validated instance, with usage and latency.

        Raises:
            ProviderError: If the call fails, the model refuses or the answer is invalid.
        """

    @abstractmethod
    def embed(self, texts: list[str], model: str) -> EmbeddingResult:
        """Generates the embeddings of a batch of texts in one call.

        Exists for the RAG ingestion and the duplicate search.

        Args:
            texts: The texts to embed; must not be empty.
            model: The catalog's `provider_model_id` of the embedding model.

        Returns:
            EmbeddingResult: one vector per text in input order, with usage and latency.

        Raises:
            ValueError: If `texts` is empty.
            ProviderError: If the call fails.
        """
