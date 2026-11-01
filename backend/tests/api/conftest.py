from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from bia.api.main import app
from bia.settings.config import get_settings


@pytest.fixture
def api_client() -> Iterator[TestClient]:
    """Provides a client that presents the shared password, as a logged-in user would.

    Exists so router tests focus on their routes; it also clears the dependency overrides
    a test installs, so they cannot leak into the next test.

    Returns:
        Iterator[TestClient]: yields the authenticated client.
    """
    client = TestClient(app)
    client.auth = ("any-user", get_settings().api_access_password.get_secret_value())
    yield client
    app.dependency_overrides.clear()
