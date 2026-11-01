import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from bia.catalog.tools.artifacts import CatalogTool, RiskLevel, ToolName
from bia.catalog.tools.consultar_factura import ConsultarFacturaTool
from bia.providers.artifacts import MessageRole, ToolCall
from bia.runtime import tools as runtime_tools
from bia.runtime.tools import ToolExecutor, to_tool_message


def _catalog_entry() -> CatalogTool:
    """Builds the catalog entry of the real tool.

    Returns:
        CatalogTool: the entry.
    """
    tool = ConsultarFacturaTool()
    return CatalogTool(
        id=uuid4(),
        name=tool.name,
        description=tool.description,
        parameters_schema=tool.parameters_schema,
        risk_level=RiskLevel.LOW,
        is_active=True,
        created_at=datetime.now(UTC),
    )


def _call(arguments: str, name: str = ToolName.CONSULTAR_FACTURA) -> ToolCall:
    """Builds a tool call as a model would write it.

    Args:
        arguments: The raw JSON arguments.
        name: The tool requested.

    Returns:
        ToolCall: the call.
    """
    return ToolCall(id="call-1", name=name, arguments=arguments)


def test_valid_call_returns_the_output_of_the_tool() -> None:
    """Verifies valid arguments reach the real tool."""
    result = ToolExecutor([_catalog_entry()]).execute(_call('{"numero_cliente": "100001"}'))

    assert result.error is None
    assert result.output == ConsultarFacturaTool().run({"numero_cliente": "100001"}).output


@pytest.mark.parametrize(
    ("arguments", "expected_error"),
    [
        ("{not json", "JSON válido"),
        ("[1, 2]", "objeto JSON"),
        ("{}", "numero_cliente"),
        ('{"numero_cliente": 100001}', "not of type"),
        ('{"numero_cliente": "1", "extra": true}', "extra"),
    ],
)
def test_invalid_arguments_become_an_error_for_the_model(
    arguments: str, expected_error: str
) -> None:
    """Verifies a model's mistake is explained to it instead of reaching the tool."""
    result = ToolExecutor([_catalog_entry()]).execute(_call(arguments))

    assert result.output is None
    assert expected_error in result.error


def test_a_tool_outside_the_spec_is_not_executed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies a registered tool stays out of reach if the agent was not assigned it."""
    monkeypatch.setattr(runtime_tools, "get_tool", _fail_if_called)

    result = ToolExecutor([]).execute(_call('{"numero_cliente": "100001"}'))

    assert "no está disponible" in result.error


def _fail_if_called(_name: str) -> None:
    """Crashes as a broken tool would, or as an access that must not happen.

    Args:
        _name: The unused tool name.

    Returns:
        None: never.

    Raises:
        RuntimeError: Always, with text that must not reach the model.
    """
    raise RuntimeError("secret-connection-string")


def test_a_crash_becomes_a_generic_error_without_internal_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies a crash does not break the loop or show internals to the model."""
    monkeypatch.setattr(runtime_tools, "get_tool", _fail_if_called)

    result = ToolExecutor([_catalog_entry()]).execute(_call('{"numero_cliente": "1"}'))

    assert "falló de forma inesperada" in result.error
    assert "secret-connection-string" not in result.error


def test_tool_id_is_known_only_for_assigned_tools() -> None:
    """Verifies the trace references the catalog and tolerates a name the model invented."""
    entry = _catalog_entry()
    executor = ToolExecutor([entry])

    assert executor.tool_id_of(entry.name) == entry.id
    assert executor.tool_id_of("invented") is None


def test_tool_message_answers_its_call_with_json() -> None:
    """Verifies errors and accents reach the model readable and tied to the right call."""
    result = ToolExecutor([]).execute(_call("{}", name="inventada"))

    message = to_tool_message(_call("{}"), result)

    assert message.role is MessageRole.TOOL
    assert message.tool_call_id == "call-1"
    assert json.loads(message.content) == {"error": "La herramienta inventada no está disponible."}
    assert "está" in message.content
