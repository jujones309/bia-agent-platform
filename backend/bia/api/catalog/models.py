from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from bia.api.dependencies import get_session
from bia.catalog.models.artifacts import CatalogModel
from bia.catalog.models.repository import (
    CatalogModelNotFoundError,
    get_catalog_model,
    list_catalog_models,
)

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=list[CatalogModel])
def list_models(
    session: Annotated[Session, Depends(get_session)], only_active: bool = False
) -> list[CatalogModel]:
    """Lists the curated model catalog.

    Exists so people and the frontend can see which models the platform offers; served as
    `GET /models`.

    Args:
        session: The session of the request.
        only_active: Whether to leave out the models that cannot be chosen for new agents.

    Returns:
        list[CatalogModel]: the matching catalog entries.
    """
    return list_catalog_models(session, only_active)


@router.get("/{model_id}", response_model=CatalogModel)
def get_model(model_id: UUID, session: Annotated[Session, Depends(get_session)]) -> CatalogModel:
    """Retrieves one entry of the model catalog.

    Exists so a `model_id` seen in a spec can be inspected; served as `GET /models/{id}`.

    Args:
        model_id: The catalog identifier of the model.
        session: The session of the request.

    Returns:
        CatalogModel: the catalog entry.

    Raises:
        HTTPException: A 404 if no entry has that identifier.
    """
    try:
        return get_catalog_model(session, model_id)
    except CatalogModelNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
