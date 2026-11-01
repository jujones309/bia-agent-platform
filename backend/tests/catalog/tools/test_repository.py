from collections.abc import Iterator

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from bia.catalog.tools.artifacts import CatalogTool, RiskLevel, ToolName
from bia.catalog.tools.consultar_factura import ConsultarFacturaTool
from bia.catalog.tools.repository import (
    deactivate_catalog_tools_except,
    list_catalog_tools,
    upsert_catalog_tool,
)
from bia.catalog.tools.sync import sync_tools
from bia.database.queries import DatabaseTable, SqlOperation, load_sql


@pytest.fixture
def session(integration_engine: Engine) -> Iterator[Session]:
    """Provides a session whose work, including the table, is rolled back at the end.

    Exists because these queries use Postgres features; rolling back keeps the target
    database untouched.

    Args:
        integration_engine: The engine of the real database.

    Returns:
        Iterator[Session]: yields the open session.
    """
    with Session(integration_engine) as open_session:
        open_session.connection().exec_driver_sql(
            load_sql(DatabaseTable.TOOLS, SqlOperation.TABLE),
            execution_options={"no_parameters": True},
        )
        yield open_session
        open_session.rollback()


class _RetiredTool(ConsultarFacturaTool):
    """Stands for a tool that was synced in the past and later left the code.

    Exists to create a catalog row outside the registry; used by the sync test.
    """

    @property
    def name(self) -> str:
        """Provides a name outside `ToolName`, as a tool removed from the code would have.

        Exists because no enum member can represent a tool that is no longer declared.

        Returns:
            str: the retired name.
        """
        return "retired_tool"


def _find_tool(session: Session, name: str) -> CatalogTool:
    """Retrieves one catalog entry by name.

    Args:
        session: The open session to read through.
        name: The name of the tool.

    Returns:
        CatalogTool: the matching entry.
    """
    return next(tool for tool in list_catalog_tools(session, False) if tool.name == name)


def test_upsert_stores_the_schema_as_json_and_reads_back_equal(session: Session) -> None:
    """Verifies the JSON Schema survives the round trip as a document, not as text."""
    tool = ConsultarFacturaTool()

    upsert_catalog_tool(session, tool)

    stored = _find_tool(session, tool.name)
    assert stored.parameters_schema == tool.parameters_schema
    assert stored.description == tool.description
    assert stored.risk_level == RiskLevel.LOW
    assert stored.is_active is True


def test_upsert_twice_refreshes_the_row_without_duplicating_it(session: Session) -> None:
    """Verifies repeated startups keep one row per tool."""
    upsert_catalog_tool(session, ConsultarFacturaTool())
    upsert_catalog_tool(session, ConsultarFacturaTool())

    names = [tool.name for tool in list_catalog_tools(session, False)]
    assert names.count(ToolName.CONSULTAR_FACTURA) == 1


def test_sync_retires_a_removed_tool_and_reactivates_a_returning_one(session: Session) -> None:
    """Verifies the table reflects the registry in both directions."""
    upsert_catalog_tool(session, _RetiredTool())
    upsert_catalog_tool(session, ConsultarFacturaTool())
    deactivate_catalog_tools_except(session, ["retired_tool"])

    sync_tools(session)

    assert _find_tool(session, "retired_tool").is_active is False
    assert _find_tool(session, ToolName.CONSULTAR_FACTURA).is_active is True


def test_list_can_leave_out_retired_tools(session: Session) -> None:
    """Verifies the designer's view cannot offer a tool whose code was removed."""
    upsert_catalog_tool(session, _RetiredTool())
    sync_tools(session)

    names = [tool.name for tool in list_catalog_tools(session, True)]

    assert "retired_tool" not in names
    assert ToolName.CONSULTAR_FACTURA in names


def test_deactivate_with_no_registered_tools_retires_everything(session: Session) -> None:
    """Verifies an empty registry is a valid array for the query, not a SQL error."""
    upsert_catalog_tool(session, ConsultarFacturaTool())

    deactivate_catalog_tools_except(session, [])

    assert list_catalog_tools(session, True) == []
