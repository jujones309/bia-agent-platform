from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from bia.catalog.models.artifacts import ModelSize
from bia.catalog.models.repository import (
    CatalogModelNotFoundError,
    EmbeddingModelUnavailableError,
    ModelSizeUnavailableError,
    find_embedding_model,
    find_model_by_size,
    get_catalog_model,
    list_catalog_models,
)
from tests.catalog.models.seed import ACTIVE_MODEL_ID, RETIRED_MODEL_ID, create_models_table


@pytest.fixture
def session() -> Iterator[Session]:
    """Provides a session on an in-memory catalog with one active and one retired model.

    Returns:
        Iterator[Session]: yields the open session.
    """
    engine = create_engine("sqlite://", poolclass=StaticPool)
    with engine.begin() as connection:
        create_models_table(connection)
    with Session(engine) as open_session:
        yield open_session


def test_list_includes_retired_models_ordered_by_name(session: Session) -> None:
    """Verifies the inventory view keeps retired models, in a stable order."""
    names = [model.name for model in list_catalog_models(session, only_active=False)]

    assert names == ["Active", "Retired"]


def test_list_can_leave_out_retired_models(session: Session) -> None:
    """Verifies the designer's view cannot offer a retired model."""
    models = list_catalog_models(session, only_active=True)

    assert [model.id for model in models] == [UUID(ACTIVE_MODEL_ID)]


def test_get_resolves_a_retired_model(session: Session) -> None:
    """Verifies an old spec that references a retired model can still be read."""
    model = get_catalog_model(session, UUID(RETIRED_MODEL_ID))

    assert model.name == "Retired"
    assert model.is_active is False


def test_get_names_the_identifier_it_could_not_find(session: Session) -> None:
    """Verifies a wrong reference fails with a clear error instead of returning nothing."""
    missing_id = uuid4()

    with pytest.raises(CatalogModelNotFoundError, match=str(missing_id)):
        get_catalog_model(session, missing_id)


def test_find_embedding_model_fails_clearly_if_only_chat_models_are_active(
    session: Session,
) -> None:
    """Verifies a chat model is never used to embed; the seeded one is covered on Postgres."""
    with pytest.raises(EmbeddingModelUnavailableError, match="no active embedding model"):
        find_embedding_model(session)


def test_find_model_by_size_skips_retired_models(session: Session) -> None:
    """Verifies a system agent is never given a retired model, though one sorts after it."""
    assert str(find_model_by_size(session, ModelSize.SMALL).id) == ACTIVE_MODEL_ID


def test_find_model_by_size_names_the_missing_size(session: Session) -> None:
    """Verifies an incomplete catalog stops the startup with a reason that says what to add."""
    with pytest.raises(ModelSizeUnavailableError, match="no active 'large' model"):
        find_model_by_size(session, ModelSize.LARGE)
