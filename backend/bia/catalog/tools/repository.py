import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from bia.catalog.tools.artifacts import CatalogTool
from bia.catalog.tools.base import Tool
from bia.database.queries import DatabaseTable, SqlOperation, load_sql


def list_catalog_tools(session: Session, only_active: bool) -> list[CatalogTool]:
    """Lists the entries of the tool catalog, ordered by name.

    Exists as the single read of the catalog; used by the tools API, and by the designer
    with `only_active` so it can only choose tools that exist in the code.

    Args:
        session: The open session to read through.
        only_active: Whether to leave out the tools that cannot be assigned to agents.

    Returns:
        list[CatalogTool]: the matching catalog entries.
    """
    sql = load_sql(DatabaseTable.TOOLS, SqlOperation.LIST)
    rows = session.execute(text(sql), {"only_active": only_active}).mappings()
    return [CatalogTool.model_validate(dict(row)) for row in rows]


def upsert_catalog_tool(session: Session, tool: Tool) -> None:
    """Creates or refreshes the catalog entry of a tool, leaving it active.

    Exists so the catalog follows the code without manual edits; used by `sync_tools`.

    Args:
        session: The open session whose transaction contains the write.
        tool: The implementation to copy the entry from.

    Returns:
        None: the row is written inside the session's transaction.
    """
    session.execute(
        text(load_sql(DatabaseTable.TOOLS, SqlOperation.UPSERT)),
        {
            "name": tool.name,
            "description": tool.description,
            "parameters_schema": json.dumps(tool.parameters_schema),
            "risk_level": tool.risk_level,
        },
    )


def deactivate_catalog_tools_except(session: Session, registered_names: list[str]) -> None:
    """Retires every active catalog tool outside the given names.

    Exists so an agent cannot be given a tool whose code was removed; used by `sync_tools`.

    Args:
        session: The open session whose transaction contains the write.
        registered_names: The names of the tools that stay active.

    Returns:
        None: the rows are updated inside the session's transaction.
    """
    session.execute(
        text(load_sql(DatabaseTable.TOOLS, SqlOperation.DEACTIVATE_EXCEPT)),
        {"registered_names": registered_names},
    )
