import hashlib

from pydantic import BaseModel

from bia.providers.artifacts import (
    ChatMessage,
    ChatResult,
    EmbeddingResult,
    MessageRole,
    StructuredChatResult,
    TokenUsage,
    ToolCall,
    ToolDefinition,
)
from bia.providers.base import ModelProvider, ProviderError

_FAKE_USAGE = TokenUsage(input_tokens=10, output_tokens=5)
_FAKE_LATENCY_MS = 1
_MAX_BYTE_VALUE = 255


class FakeModelProvider(ModelProvider):
    """Replaces real LLMs in tests with scripted answers.

    Exists because tests never call the real API; consumed by the tests of every vertical
    that depends on `ModelProvider`. Lives under `tests/` so it can never reach production.
    Answers are consumed in the order they were queued, and running out of them fails the
    test instead of inventing a response.
    """

    def __init__(self, embedding_dimensions: int = 8) -> None:
        """Starts with nothing scripted.

        Args:
            embedding_dimensions (int): The length of the vectors `embed` returns.
        """
        self._embedding_dimensions = embedding_dimensions
        self._chat_answers: list[ChatMessage | ProviderError] = []
        self._structured_answers: list[BaseModel | ProviderError] = []
        self.chat_requests: list[list[ChatMessage]] = []
        self.offered_tools: list[list[ToolDefinition] | None] = []
        self.requested_models: list[str] = []

    def queue_text(self, text: str) -> None:
        """Scripts a final text answer for the next `chat` call.

        Args:
            text: The content of the assistant's message.
        """
        self._chat_answers.append(ChatMessage(role=MessageRole.ASSISTANT, content=text))

    def queue_tool_calls(self, tool_calls: list[ToolCall]) -> None:
        """Scripts a tool request for the next `chat` call.

        Args:
            tool_calls: The tools the model asks to run.
        """
        self._chat_answers.append(ChatMessage(role=MessageRole.ASSISTANT, tool_calls=tool_calls))

    def queue_chat_error(self, error: ProviderError) -> None:
        """Scripts a failure for the next `chat` call.

        Args:
            error: The error the call raises.
        """
        self._chat_answers.append(error)

    def queue_structured(self, answer: BaseModel | ProviderError) -> None:
        """Scripts the result of the next `chat_structured` call.

        Args:
            answer: The instance the call returns, or the error it raises.
        """
        self._structured_answers.append(answer)

    def chat(
        self,
        messages: list[ChatMessage],
        model: str,
        tools: list[ToolDefinition] | None = None,
    ) -> ChatResult:
        """Returns the next scripted answer, recording the request.

        Exists so tests can assert what the code under test sent and simulate the model.

        Args:
            messages: The conversation so far.
            model: The model requested.
            tools: The tools offered.

        Returns:
            ChatResult: the scripted message with fixed usage and latency.

        Raises:
            ProviderError: If that is what was scripted.
        """
        self.chat_requests.append(list(messages))
        self.offered_tools.append(tools)
        self.requested_models.append(model)
        answer = _next_answer(self._chat_answers)
        return ChatResult(message=answer, usage=_FAKE_USAGE, latency_ms=_FAKE_LATENCY_MS)

    def chat_structured[ResponseT: BaseModel](
        self,
        messages: list[ChatMessage],
        response_model: type[ResponseT],
        model: str,
    ) -> StructuredChatResult[ResponseT]:
        """Returns the next scripted instance, recording the request.

        Exists so tests simulate judges and the designer. Rejects an instance of another
        type, because a real provider could never return it.

        Args:
            messages: The conversation so far.
            response_model: The type the caller expects.
            model: The model requested.

        Returns:
            StructuredChatResult[ResponseT]: the instance with fixed usage and latency.

        Raises:
            ProviderError: If that is what was scripted.
            TypeError: If the scripted instance is not a `response_model`.
        """
        self.chat_requests.append(list(messages))
        self.requested_models.append(model)
        answer = _next_answer(self._structured_answers)
        if not isinstance(answer, response_model):
            raise TypeError(f"Scripted {type(answer).__name__}, not {response_model.__name__}")
        return StructuredChatResult[response_model](
            parsed=answer, usage=_FAKE_USAGE, latency_ms=_FAKE_LATENCY_MS
        )

    def embed(self, texts: list[str], model: str) -> EmbeddingResult:
        """Generates a deterministic vector per text.

        Exists so equal texts get equal vectors and different texts get different ones,
        without scripting anything.

        Args:
            texts: The texts to embed; must not be empty, as in real providers.
            model: The model requested.

        Returns:
            EmbeddingResult: one vector per text in order, with fixed usage and latency.

        Raises:
            ValueError: If `texts` is empty.
        """
        if not texts:
            raise ValueError("Cannot embed an empty list of texts")
        self.requested_models.append(model)
        return EmbeddingResult(
            embeddings=[self._embed_text(text) for text in texts],
            usage=TokenUsage(input_tokens=len(texts), output_tokens=0),
            latency_ms=_FAKE_LATENCY_MS,
        )

    def _embed_text(self, text: str) -> list[float]:
        """Derives a vector from the hash of a text.

        Args:
            text: The text to embed.

        Returns:
            list[float]: the vector, with values between 0 and 1.
        """
        digest = hashlib.shake_128(text.encode()).digest(self._embedding_dimensions)
        return [byte / _MAX_BYTE_VALUE for byte in digest]


def _next_answer[AnswerT](answers: list[AnswerT | ProviderError]) -> AnswerT:
    """Takes the next scripted answer, raising it if it is an error.

    Args:
        answers: The queue of scripted answers.

    Returns:
        AnswerT: the next answer.

    Raises:
        ProviderError: If the scripted answer is an error.
        AssertionError: If the test did not script enough answers.
    """
    if not answers:
        raise AssertionError("FakeModelProvider received a call with no scripted answer left")
    answer = answers.pop(0)
    if isinstance(answer, ProviderError):
        raise answer
    return answer
