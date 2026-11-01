import logging

from sqlalchemy.orm import Session

from bia.catalog.tools.registry import list_registered_tools
from bia.catalog.tools.repository import deactivate_catalog_tools_except, upsert_catalog_tool

logger = logging.getLogger(__name__)


def sync_tools(session: Session) -> None:
    """Makes the `tools` table reflect the code registry.

    Exists because tools are implemented in code but agents and the designer read them
    from the catalog, and the two must not drift. Every registered tool ends up active and
    every other tool inactive, so `is_active` is owned by the registry. Used at application
    startup by `bia/api/main.py`.

    Args:
        session: The open session whose transaction contains the sync.

    Returns:
        None: the catalog is updated inside the session's transaction.
    """
    tools = list_registered_tools()
    for tool in tools:
        upsert_catalog_tool(session, tool)
    deactivate_catalog_tools_except(session, [tool.name.value for tool in tools])
    logger.info("Synced %d tools to the catalog", len(tools))
