from bia.providers.artifacts import ChatMessage, MessageRole, ToolCall, ToolDefinition
from bia.providers.openai.mapping import to_wire_items, to_wire_tool

_TOOL_CALL = ToolCall(id="call-1", name="consultar_factura", arguments='{"cliente":"1"}')
_WIRE_TOOL_CALL = {
    "type": "function_call",
    "call_id": "call-1",
    "name": "consultar_factura",
    "arguments": '{"cliente":"1"}',
}


def test_user_message_becomes_one_item_without_tool_keys() -> None:
    """Verifies a plain message carries only its role and content."""
    message = ChatMessage(role=MessageRole.USER, content="Hola")

    assert to_wire_items(message) == [{"role": "user", "content": "Hola"}]


def test_assistant_tool_request_can_be_replayed() -> None:
    """Verifies the raw arguments and the id survive, or the loop's next turn would be rejected."""
    message = ChatMessage(role=MessageRole.ASSISTANT, tool_calls=[_TOOL_CALL])

    assert to_wire_items(message) == [_WIRE_TOOL_CALL]


def test_assistant_text_with_tool_calls_keeps_both_in_order() -> None:
    """Verifies neither part of a mixed message is lost when it is split into items."""
    message = ChatMessage(role=MessageRole.ASSISTANT, content="Consulto", tool_calls=[_TOOL_CALL])

    assert to_wire_items(message) == [
        {"role": "assistant", "content": "Consulto"},
        _WIRE_TOOL_CALL,
    ]


def test_tool_result_references_the_call_it_answers() -> None:
    """Verifies a tool result stays linked to its call."""
    message = ChatMessage(role=MessageRole.TOOL, content="100", tool_call_id="call-1")

    assert to_wire_items(message) == [
        {"type": "function_call_output", "call_id": "call-1", "output": "100"}
    ]


def test_tool_definition_disables_strict_mode() -> None:
    """Verifies the schema travels as given, since strict mode would reject ordinary schemas."""
    schema = {"type": "object", "properties": {"cliente": {"type": "string"}}}
    tool = ToolDefinition(name="consultar", description="Consulta", parameters_schema=schema)

    assert to_wire_tool(tool) == {
        "type": "function",
        "name": "consultar",
        "description": "Consulta",
        "parameters": schema,
        "strict": False,
    }
