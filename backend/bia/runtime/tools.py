import json
import logging
from uuid import UUID

import jsonschema

from bia.catalog.tools.artifacts import CatalogTool, ToolResult
from bia.catalog.tools.registry import get_tool
from bia.providers.artifacts import ChatMessage, MessageRole, ToolCall, ToolDefinition

logger = logging.getLogger(__name__)

_ERROR_KEY = "error"


class _InvalidToolArgumentsError(ValueError):
    """Signals that the model sent arguments a tool cannot accept.

    Exists to carry the message for the model out of `_parse_arguments`; handled by
    `ToolExecutor.execute`.
    """


def _parse_arguments(raw_arguments: str, schema: dict[str, object]) -> dict[str, object]:
    """Parses the JSON a model wrote and validates it against a tool's schema.

    Exists because models can write invalid JSON or wrong arguments, and tools trust what
    they receive; used by `ToolExecutor.execute`.

    Args:
        raw_arguments: The arguments as the model wrote them.
        schema: The JSON Schema of the tool's arguments.

    Returns:
        dict[str, object]: the validated arguments.

    Raises:
        _InvalidToolArgumentsError: If the arguments are not valid, in words for the model.
    """
    try:
        arguments = json.loads(raw_arguments)
    except json.JSONDecodeError as error:
        raise _InvalidToolArgumentsError(f"Los argumentos no son JSON válido: {error}") from error
    if not isinstance(arguments, dict):
        raise _InvalidToolArgumentsError("Los argumentos deben ser un objeto JSON.")
    try:
        jsonschema.validate(arguments, schema)
    except jsonschema.ValidationError as error:
        raise _InvalidToolArgumentsError(f"Argumentos inválidos: {error.message}") from error
    return arguments


def _run_tool(tool_name: str, arguments: dict[str, object]) -> ToolResult:
    """Runs a tool, turning a crash into an error result.

    Exists so a bug in one tool does not end the conversation. The model only gets a generic
    message because exception details can expose internals; they go to the operators' logs.
    Used by `ToolExecutor.execute`.

    Args:
        tool_name: The name of the tool.
        arguments: The validated arguments.

    Returns:
        ToolResult: what the tool returned, or an error if it crashed.
    """
    try:
        return get_tool(tool_name).run(arguments)
    except Exception:
        logger.exception("Tool %s crashed", tool_name)
        return ToolResult(error=f"La herramienta {tool_name} falló de forma inesperada.")


def to_tool_message(tool_call: ToolCall, result: ToolResult) -> ChatMessage:
    """Converts the result of a tool to the message that answers its call.

    Exists so successes and failures reach the model in one format; used by `AgentRunner`.

    Args:
        tool_call: The call being answered.
        result: What the execution produced.

    Returns:
        ChatMessage: the message for the model, with the result as JSON.
    """
    payload = result.output if result.error is None else {_ERROR_KEY: result.error}
    return ChatMessage(
        role=MessageRole.TOOL,
        content=json.dumps(payload, ensure_ascii=False),
        tool_call_id=tool_call.id,
    )


class ToolExecutor:
    """Runs the tool calls of a model, limited to the tools its agent was assigned.

    Exists so a model can never reach a tool outside its spec, and so every mistake becomes
    information for the model instead of breaking the loop. Consumed by `AgentRunner`.
    """

    def __init__(self, assigned_tools: list[CatalogTool]) -> None:
        """Creates an executor for the tools of one agent.

        Args:
            assigned_tools (list[CatalogTool]): The catalog entries the agent may call.
        """
        self._tools_by_name = {tool.name: tool for tool in assigned_tools}

    def definitions(self) -> list[ToolDefinition]:
        """Builds the definitions offered to the model.

        Exists so the model only learns about the assigned tools; used on every model call.

        Returns:
            list[ToolDefinition]: one definition per assigned tool.
        """
        return [
            ToolDefinition(
                name=tool.name,
                description=tool.description,
                parameters_schema=tool.parameters_schema,
            )
            for tool in self._tools_by_name.values()
        ]

    def tool_id_of(self, tool_name: str) -> UUID | None:
        """Finds the catalog identifier of a tool the model named.

        Exists so the trace can reference the tool; used when recording a tool step.

        Args:
            tool_name: The name the model used.

        Returns:
            UUID | None: the identifier, or None if the agent has no such tool.
        """
        tool = self._tools_by_name.get(tool_name)
        return tool.id if tool else None

    def execute(self, tool_call: ToolCall) -> ToolResult:
        """Validates and runs one tool call, without ever raising for a model's mistake.

        Exists as the single way the loop runs a tool.

        Args:
            tool_call: The call the model requested.

        Returns:
            ToolResult: the output, or the error to show the model.
        """
        tool = self._tools_by_name.get(tool_call.name)
        if tool is None:
            return ToolResult(error=f"La herramienta {tool_call.name} no está disponible.")
        try:
            arguments = _parse_arguments(tool_call.arguments, tool.parameters_schema)
        except _InvalidToolArgumentsError as error:
            return ToolResult(error=str(error))
        return _run_tool(tool.name, arguments)
