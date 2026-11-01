from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from bia.catalog.models.artifacts import CatalogModel
from bia.database.queries import DatabaseTable, SqlOperation, load_sql


class CatalogModelNotFoundError(LookupError):
    """Signals that the model catalog has no entry with the requested identifier.

    Exists so consumers can tell a wrong reference from a database failure. Raised by
    `get_catalog_model` and translated to a 404 by `bia/api/catalog/models.py`.
    """


def list_catalog_models(session: Session, only_active: bool) -> list[CatalogModel]:
    """Lists the entries of the model catalog, ordered by name.

    Exists as the single read of the catalog; used by the models API, and by the designer
    with `only_active` so it can only choose models available for new agents.

    Args:
        session: The open session to read through.
        only_active: Whether to leave out the models that cannot be chosen for new agents.

    Returns:
        list[CatalogModel]: the matching catalog entries.
    """
    sql = load_sql(DatabaseTable.MODELS, SqlOperation.LIST)
    rows = session.execute(text(sql), {"only_active": only_active}).mappings()
    return [CatalogModel.model_validate(dict(row)) for row in rows]


def get_catalog_model(session: Session, model_id: UUID) -> CatalogModel:
    """Retrieves one entry of the model catalog, active or not.

    Exists so a spec's `model_id` resolves to its provider and prices, even when the model
    was retired after the spec was written; used by the models API.

    Args:
        session: The open session to read through.
        model_id: The catalog identifier of the model.

    Returns:
        CatalogModel: the catalog entry.

    Raises:
        CatalogModelNotFoundError: If no entry has that identifier.
    """
    sql = load_sql(DatabaseTable.MODELS, SqlOperation.GET_BY_ID)
    row = session.execute(text(sql), {"model_id": str(model_id)}).mappings().one_or_none()
    if row is None:
        raise CatalogModelNotFoundError(f"The model catalog has no entry with id {model_id}")
    return CatalogModel.model_validate(dict(row))
