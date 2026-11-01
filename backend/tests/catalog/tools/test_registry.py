import pytest

from bia.catalog.tools.artifacts import ToolName
from bia.catalog.tools.base import UnknownToolError
from bia.catalog.tools.consultar_factura import ConsultarFacturaTool
from bia.catalog.tools.registry import get_tool, list_registered_tools


def test_get_tool_resolves_the_text_stored_in_a_spec() -> None:
    """Verifies a spec's plain text reaches the right implementation."""
    assert isinstance(get_tool("consultar_factura"), ConsultarFacturaTool)


@pytest.mark.parametrize("tool_name", list(ToolName))
def test_every_declared_tool_is_registered_under_its_own_name(tool_name: ToolName) -> None:
    """Verifies an enum member without a builder, or a builder under a wrong key, is caught."""
    assert get_tool(tool_name).name == tool_name


def test_list_registered_tools_returns_every_declared_tool() -> None:
    """Verifies the catalog sync cannot miss a tool."""
    assert {tool.name for tool in list_registered_tools()} == set(ToolName)


def test_get_tool_names_the_rejected_value_and_the_options() -> None:
    """Verifies a name invented by a model fails saying what was asked and what is valid."""
    with pytest.raises(UnknownToolError, match="'borrar_todo'.*Supported tools: consultar_factura"):
        get_tool("borrar_todo")
