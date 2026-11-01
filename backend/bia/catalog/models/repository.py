from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from bia.catalog.models.artifacts import CatalogModel, ModelSize
from bia.database.queries import DatabaseTable, SqlOperation, load_sql


class CatalogModelNotFoundError(LookupError):
    """Signals that the model catalog has no entry with the requested identifier.

    Exists so consumers can tell a wrong reference from a database failure. Raised by
    `get_catalog_model` and translated to a 404 by `bia/api/catalog/models.py`.
    """


class EmbeddingModelUnavailableError(LookupError):
    """Signals that the model catalog has no active embedding model.

    Exists because neither agent descriptions nor knowledge can be embedded without one. Raised
    by `find_embedding_model` and translated to a 503 by `bia/api/`.
    """


class ModelSizeUnavailableError(LookupError):
    """Signals that the model catalog has no active model of the size a system agent needs.

    Exists so an unseeded catalog stops the startup with a clear reason. Raised by
    `find_model_by_size`.
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


def find_model_by_size(session: Session, size: ModelSize) -> CatalogModel:
    """Chooses an active catalog model of the given size.

    Exists because model identifiers always come from the catalog; used to assign a model to the
    system agents when they are first registered.

    Args:
        session: The open session to read the catalog through.
        size: The size the caller needs.

    Returns:
        CatalogModel: the first active model of that size, by name.

    Raises:
        ModelSizeUnavailableError: If the catalog has none.
    """
    for model in list_catalog_models(session, only_active=True):
        if model.size is size:
            return model
    raise ModelSizeUnavailableError(f"The model catalog has no active '{size}' model")


def find_embedding_model(session: Session) -> CatalogModel:
    """Chooses the catalog model that generates embeddings.

    Exists because model identifiers always come from the catalog; used by the agent registry
    and by the RAG ingestion and search.

    Args:
        session: The open session to read the catalog through.

    Returns:
        CatalogModel: the first active embedding model, by name.

    Raises:
        EmbeddingModelUnavailableError: If the catalog has none.
    """
    for model in list_catalog_models(session, only_active=True):
        if model.size is ModelSize.EMBEDDING:
            return model
    raise EmbeddingModelUnavailableError("The model catalog has no active embedding model")
