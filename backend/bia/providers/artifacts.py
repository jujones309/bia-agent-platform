from enum import StrEnum

from pydantic import BaseModel, Field


class ProviderName(StrEnum):
    """The model providers the platform can talk to.

    Exists so a provider is always one option of a closed set; stored in the model catalog
    and consumed by `get_provider` in `bia/providers/factory.py`.
    """

    OPENAI = "openai"


class MessageRole(StrEnum):
    """The authors a message of a conversation can have.

    Exists so conversations are provider-agnostic; set by the runtime and the builder and
    translated to each provider's wire format by its implementation.
    """

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"  # the result of a tool call, sent back to the model


class ToolCall(BaseModel):
    """Describes a tool the model asked to run.

    Exists as the provider-agnostic form of a tool request; produced by providers and
    consumed by the runtime's tool-calling loop.
    """

    id: str
    name: str
    arguments: str  # raw JSON as the model wrote it; may be invalid, the runtime validates it


class ToolDefinition(BaseModel):
    """Describes a tool offered to the model.

    Exists so callers declare tools without knowing the provider's format; built by the
    runtime from the tool catalog and consumed by `ModelProvider.chat`.
    """

    name: str
    description: str
    parameters_schema: dict[str, object]  # JSON schema of the tool's arguments


class ChatMessage(BaseModel):
    """Represents one message of a conversation.

    Exists as the single conversation format of the platform; assembled by the runtime and
    the builder, sent through `ModelProvider` and returned inside `ChatResult`.
    """

    role: MessageRole
    content: str | None = None  # None when an assistant message only requests tools
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None  # the call being answered, only for the tool role


class TokenUsage(BaseModel):
    """Counts the tokens consumed by one provider call.

    Exists so tracing and cost calculation read one format; produced by providers and
    consumed by `compute_cost` and `bia/tracing/`.
    """

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class ChatResult(BaseModel):
    """Holds the outcome of a chat call.

    Exists to return the model's message with the data every traced call must record;
    produced by `ModelProvider.chat` and consumed by the runtime.
    """

    message: ChatMessage
    usage: TokenUsage
    latency_ms: int = Field(ge=0)


class StructuredChatResult[ResponseT: BaseModel](BaseModel):
    """Holds the outcome of a chat call that must return structured data.

    Exists because returning only the validated instance would lose the usage and latency
    every LLM call must trace; produced by `ModelProvider.chat_structured` and consumed by
    the builder and the evals.
    """

    parsed: ResponseT
    usage: TokenUsage
    latency_ms: int = Field(ge=0)


class EmbeddingResult(BaseModel):
    """Holds the outcome of an embedding call.

    Exists to return the vectors with the data every traced call must record; produced by
    `ModelProvider.embed` and consumed by the RAG ingestion and the duplicate search.
    """

    embeddings: list[list[float]]  # one vector per input text, in the same order
    usage: TokenUsage
    latency_ms: int = Field(ge=0)
