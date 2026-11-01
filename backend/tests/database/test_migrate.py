from sqlalchemy import Engine, column, select, table

from bia.database.connection import database_session
from bia.database.migrate import apply_schema, apply_seeds
from bia.database.queries import DatabaseTable

_PG_TABLES = table("pg_tables", column("tablename"), column("schemaname"))
_MODELS = table("models", column("size"), column("input_cost_per_million"))


def test_migration_can_run_twice_and_creates_every_table(integration_engine: Engine) -> None:
    """Verifies the migration is idempotent and leaves the whole schema in place."""
    for _ in range(2):
        with database_session(integration_engine) as session:
            apply_schema(session)

    with database_session(integration_engine) as session:
        query = select(_PG_TABLES.c.tablename).where(_PG_TABLES.c.schemaname == "public")
        existing = set(session.scalars(query))

    assert set(DatabaseTable) <= existing


def test_seeds_can_run_twice_without_duplicating_models(integration_engine: Engine) -> None:
    """Verifies the catalog keeps one priced model per size after repeated seeding."""
    for _ in range(2):
        with database_session(integration_engine) as session:
            apply_schema(session)
            apply_seeds(session)

    with database_session(integration_engine) as session:
        rows = session.execute(select(_MODELS)).all()

    assert sorted(row.size for row in rows) == ["embedding", "large", "small"]
    assert all(row.input_cost_per_million > 0 for row in rows)
