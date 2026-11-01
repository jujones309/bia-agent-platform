from enum import StrEnum

from openai.types.create_embedding_response import Usage as EmbeddingUsage
from openai.types.responses import (
    Response,
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputRefusal,
    ResponseUsage,
)

from bia.providers.artifacts import (
    ChatMessage,
    MessageRole,
    TokenUsage,
    ToolCall,
    ToolDefinition,
)
from bia.providers.base import ProviderError


class _WireItemType(StrEnum):
    """The input item types of OpenAI's Responses API used by the tool-calling loop.

    Exists to avoid raw literals in the wire format; consumed by the conversions below.
    """

    FUNCTION = "function"  # the type of a tool definition
    FUNCTION_CALL = "function_call"
    FUNCTION_CALL_OUTPUT = "function_call_output"


class _ResponseStatus(StrEnum):
    """The status of a Responses API response that holds a complete answer.

    Exists so any other status is rejected instead of being treated as final; consumed by
    `ensure_usable_response`.
    """

    COMPLETED = "completed"


def _to_wire_tool_call(tool_call: ToolCall) -> dict[str, object]:
    """Converts a tool call to an input item of the Responses API.

    Exists so previous tool requests can be replayed in the tool-calling loop; used by
    `to_wire_items`.

    Args:
        tool_call: The tool call to convert.

    Returns:
        dict[str, object]: the item as the API expects it.
    """
    return {
        "type": _WireItemType.FUNCTION_CALL,
        "call_id": tool_call.id,
        "name": tool_call.name,
        "arguments": tool_call.arguments,
    }


def to_wire_items(message: ChatMessage) -> list[dict[str, object]]:
    """Converts a message to input items of the Responses API.

    Exists to keep the wire format out of the rest of the platform; used by
    `OpenAIModelProvider`. Returns a list because the API represents text and each tool
    call of one assistant message as separate items.

    Args:
        message: The message to convert.

    Returns:
        list[dict[str, object]]: the items as the API expects them.
    """
    if message.role == MessageRole.TOOL:
        return [
            {
                "type": _WireItemType.FUNCTION_CALL_OUTPUT,
                "call_id": message.tool_call_id,
                "output": message.content,
            }
        ]
    text_items = [{"role": message.role, "content": message.content}] if message.content else []
    return text_items + [_to_wire_tool_call(call) for call in message.tool_calls]


def to_wire_tool(tool: ToolDefinition) -> dict[str, object]:
    """Converts a tool definition to the format of the Responses API.

    Exists to keep the wire format out of the rest of the platform; used by
    `OpenAIModelProvider.chat`. Disables strict mode, which the API would otherwise apply
    and which rejects ordinary JSON schemas; the runtime validates the arguments instead.

    Args:
        tool: The tool to convert.

    Returns:
        dict[str, object]: the tool as the API expects it.
    """
    return {
        "type": _WireItemType.FUNCTION,
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.parameters_schema,
        "strict": False,
    }


def _find_refusal(response: Response) -> str | None:
    """Looks for a refusal among the output of a response.

    Exists because a refusal arrives as regular output with a status of completed; used by
    `ensure_usable_response`.

    Args:
        response: The API response.

    Returns:
        str | None: the refusal text, or None if the model did not refuse.
    """
    for item in response.output:
        if not isinstance(item, ResponseOutputMessage):
            continue
        for part in item.content:
            if isinstance(part, ResponseOutputRefusal):
                return part.refusal
    return None


def ensure_usable_response(response: Response) -> None:
    """Rejects responses that do not hold a complete answer.

    Exists so truncated, failed or refused answers fail here and never reach an agent as
    if they were final; used by `OpenAIModelProvider`.

    Args:
        response: The API response.

    Raises:
        ProviderError: If the response is incomplete, failed or a refusal.
    """
    if response.status != _ResponseStatus.COMPLETED:
        details = response.incomplete_details or response.error
        raise ProviderError(f"OpenAI response is {response.status}: {details}")
    refusal = _find_refusal(response)
    if refusal:
        raise ProviderError(f"OpenAI model refused to answer: {refusal}")


def to_chat_message(response: Response) -> ChatMessage:
    """Converts the output of a response to the platform's message format.

    Exists to keep the SDK's types out of the rest of the platform; used by
    `OpenAIModelProvider.chat`.

    Args:
        response: A response already accepted by `ensure_usable_response`.

    Returns:
        ChatMessage: the equivalent assistant message.

    Raises:
        ProviderError: If the response holds neither text nor tool calls.
    """
    tool_calls = [
        ToolCall(id=item.call_id, name=item.name, arguments=item.arguments)
        for item in response.output
        if isinstance(item, ResponseFunctionToolCall)
    ]
    content = response.output_text or None
    if content is None and not tool_calls:
        raise ProviderError("OpenAI returned an empty message")
    return ChatMessage(role=MessageRole.ASSISTANT, content=content, tool_calls=tool_calls)


def to_response_usage(usage: ResponseUsage | None) -> TokenUsage:
    """Converts the usage of a response.

    Exists because every LLM call must be traced, so a response without usage is an error
    and not a call that costs zero; used by `OpenAIModelProvider`.

    Args:
        usage: The usage reported by the API.

    Returns:
        TokenUsage: the tokens the call consumed.

    Raises:
        ProviderError: If the response did not report usage.
    """
    if usage is None:
        raise ProviderError("OpenAI returned a response without usage")
    return TokenUsage(input_tokens=usage.input_tokens, output_tokens=usage.output_tokens)


def to_embedding_usage(usage: EmbeddingUsage) -> TokenUsage:
    """Converts the usage of an embedding call.

    Exists because embeddings report only input tokens; used by
    `OpenAIModelProvider.embed`.

    Args:
        usage: The usage reported by the API.

    Returns:
        TokenUsage: the tokens the call consumed, with no output tokens.
    """
    return TokenUsage(input_tokens=usage.prompt_tokens, output_tokens=0)
