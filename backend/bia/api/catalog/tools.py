from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from bia.api.dependencies import get_session
from bia.catalog.tools.artifacts import CatalogTool
from bia.catalog.tools.repository import list_catalog_tools

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("", response_model=list[CatalogTool])
def list_tools(
    session: Annotated[Session, Depends(get_session)], only_active: bool = False
) -> list[CatalogTool]:
    """Lists the curated tool catalog.

    Exists so people and the frontend can see which tools agents may use; served as
    `GET /tools`.

    Args:
        session: The session of the request.
        only_active: Whether to leave out the tools that cannot be assigned to agents.

    Returns:
        list[CatalogTool]: the matching catalog entries.
    """
    return list_catalog_tools(session, only_active)
