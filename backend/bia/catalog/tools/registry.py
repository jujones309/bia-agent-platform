from collections.abc import Callable
from functools import lru_cache

from bia.catalog.tools.artifacts import ToolName
from bia.catalog.tools.base import Tool, UnknownToolError
from bia.catalog.tools.consultar_factura import ConsultarFacturaTool

_TOOL_BUILDERS: dict[ToolName, Callable[[], Tool]] = {
    ToolName.CONSULTAR_FACTURA: ConsultarFacturaTool,
}


@lru_cache
def _build_tool(tool_name: ToolName) -> Tool:
    """Builds a tool once per process.

    Exists so all consumers share one instance and its loaded data; used by `get_tool` and
    `list_registered_tools`.

    Args:
        tool_name: The tool to build.

    Returns:
        Tool: the cached tool.
    """
    return _TOOL_BUILDERS[tool_name]()


def get_tool(tool_name: str) -> Tool:
    """Retrieves the implementation of a tool from its name.

    Exists so the runtime goes from a name in a spec, or in a model's tool call, to code
    without importing any implementation. Accepts plain text because that is how both
    store the name.

    Args:
        tool_name: A `ToolName` member or its text value.

    Returns:
        Tool: the shared tool implementation.

    Raises:
        UnknownToolError: If the name has no implementation.
    """
    if tool_name not in list(ToolName):
        supported = ", ".join(ToolName)
        raise UnknownToolError(f"Unknown tool '{tool_name}'. Supported tools: {supported}")
    return _build_tool(ToolName(tool_name))


def list_registered_tools() -> list[Tool]:
    """Lists every tool implemented in the code.

    Exists as the source of truth of the catalog sync in `bia/catalog/tools/sync.py`.

    Returns:
        list[Tool]: the shared tool implementations.
    """
    return [_build_tool(tool_name) for tool_name in _TOOL_BUILDERS]
