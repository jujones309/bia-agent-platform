from sqlalchemy import Connection
from sqlalchemy.schema import Column, MetaData, Table
from sqlalchemy.types import Boolean, Integer, Numeric, String

ACTIVE_MODEL_ID = "6f1c7c1e-0d6b-4a57-9a53-0f6f3f0a1b2c"
RETIRED_MODEL_ID = "7a2d8d2f-1e7c-4b68-8b64-1a7a4a1b2c3d"


def _model_row(model_id: str, name: str, is_active: bool) -> dict[str, object]:
    """Builds a row of the `models` table that differs only in the given values.

    Args:
        model_id: The catalog identifier of the model.
        name: The readable name, which also orders the listing.
        is_active: Whether the model can be chosen for new agents.

    Returns:
        dict[str, object]: the column values of the row.
    """
    return {
        "id": model_id,
        "name": name,
        "provider": "openai",
        "provider_model_id": name.lower(),
        "size": "small",
        "input_cost_per_million": "0.10",
        "output_cost_per_million": "0.50",
        "context_window": 1000,
        "recommended_use": "Tests",
        "is_active": is_active,
        "created_at": "2026-10-31T00:00:00Z",
    }


def create_models_table(connection: Connection) -> None:
    """Creates a portable copy of the `models` table with one active and one retired model.

    Exists so the real catalog queries run in every test run, on SQLite, without needing
    Postgres; used by the unit tests of the repository and of the API.

    Args:
        connection: The connection to the empty test database.

    Returns:
        None: the table and its rows are created in place.
    """
    table = Table(
        "models",
        MetaData(),
        Column("id", String, primary_key=True),
        Column("name", String),
        Column("provider", String),
        Column("provider_model_id", String),
        Column("size", String),
        Column("input_cost_per_million", Numeric),
        Column("output_cost_per_million", Numeric),
        Column("context_window", Integer),
        Column("recommended_use", String),
        Column("is_active", Boolean),
        Column("created_at", String),
    )
    table.create(connection)
    connection.execute(
        table.insert(),
        [
            _model_row(RETIRED_MODEL_ID, "Retired", False),
            _model_row(ACTIVE_MODEL_ID, "Active", True),
        ],
    )
