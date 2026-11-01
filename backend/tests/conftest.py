import os

import pytest
from sqlalchemy import Engine

from bia.database.connection import create_database_engine

# Set before any test module imports bia.api.main, which validates settings on import.
# Process variables take precedence over backend/.env, so tests never see real secrets.
os.environ["OPENAI_API_KEY"] = "test-openai-key"
os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/test"
os.environ["API_ACCESS_PASSWORD"] = "test-access-password"
os.environ["ENVIRONMENT"] = "test"
os.environ["LOG_LEVEL"] = "INFO"


@pytest.fixture
def integration_engine() -> Engine:
    """Provides an engine to a real database, or skips the test if none was given.

    Exists so integration tests only run on explicit request and never reach the database
    in `backend/.env` by accident.

    Returns:
        Engine: an engine connected to `INTEGRATION_DATABASE_URL`.
    """
    database_url = os.environ.get("INTEGRATION_DATABASE_URL")
    if not database_url:
        pytest.skip("INTEGRATION_DATABASE_URL is not set")
    return create_database_engine(database_url)
