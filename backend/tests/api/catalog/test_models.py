from collections.abc import Iterator
from functools import partial
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from bia.api.dependencies import get_session
from bia.api.main import app
from tests.catalog.models.seed import ACTIVE_MODEL_ID, RETIRED_MODEL_ID, create_models_table


@pytest.fixture
def client(api_client: TestClient) -> TestClient:
    """Provides an authenticated client whose routes read an in-memory catalog.

    Args:
        api_client: The authenticated client.

    Returns:
        TestClient: the client, with the database dependency replaced.
    """
    # The API runs routes on worker threads, so the one connection must be shareable.
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    with engine.begin() as connection:
        create_models_table(connection)
    app.dependency_overrides[get_session] = partial(_open_session, engine)
    return api_client


def _open_session(engine: Engine) -> Iterator[Session]:
    """Opens the session a test route reads through.

    Args:
        engine: The engine of the in-memory catalog.

    Returns:
        Iterator[Session]: yields the open session.
    """
    with Session(engine) as session:
        yield session


def test_list_returns_every_model_by_default(client: TestClient) -> None:
    """Verifies the inventory shows retired models, with exact prices."""
    response = client.get("/models")

    assert response.status_code == 200
    assert [model["id"] for model in response.json()] == [ACTIVE_MODEL_ID, RETIRED_MODEL_ID]
    assert float(response.json()[0]["input_cost_per_million"]) == 0.10


def test_list_can_be_filtered_to_active_models(client: TestClient) -> None:
    """Verifies the query parameter reaches the catalog filter."""
    response = client.get("/models", params={"only_active": True})

    assert [model["id"] for model in response.json()] == [ACTIVE_MODEL_ID]


def test_get_returns_the_requested_model(client: TestClient) -> None:
    """Verifies the path identifier selects the right entry."""
    response = client.get(f"/models/{RETIRED_MODEL_ID}")

    assert response.status_code == 200
    assert response.json()["name"] == "Retired"


def test_get_answers_404_for_an_unknown_model(client: TestClient) -> None:
    """Verifies a missing entry is a client error that names the identifier, not a 500."""
    missing_id = uuid4()

    response = client.get(f"/models/{missing_id}")

    assert response.status_code == 404
    assert str(missing_id) in response.json()["detail"]


def test_get_answers_422_for_a_malformed_identifier(client: TestClient) -> None:
    """Verifies a malformed identifier is rejected before reaching the database."""
    assert client.get("/models/not-a-uuid").status_code == 422


def test_models_require_credentials() -> None:
    """Verifies the catalog stays behind the shared password."""
    assert TestClient(app).get("/models").status_code == 401
