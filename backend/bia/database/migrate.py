import logging

from sqlalchemy.orm import Session

from bia.database.connection import database_session, get_engine
from bia.database.queries import DatabaseTable, SqlOperation, load_sql
from bia.settings.config import get_settings

logger = logging.getLogger(__name__)

_SEEDED_TABLES = (DatabaseTable.MODELS,)
_NO_PARAMETERS_OPTION = {"no_parameters": True}


def _execute_script(session: Session, table: DatabaseTable, operation: SqlOperation) -> None:
    """Executes a SQL file that may hold several statements.

    Exists because the driver only accepts multiple statements when no parameters are
    involved, which has to be requested explicitly; used by `apply_schema` and `apply_seeds`.

    Args:
        session: The open session whose transaction contains the script.
        table: The table whose file is executed.
        operation: The operation that names the file.

    Returns:
        None: the script is executed inside the session's transaction.
    """
    session.connection().exec_driver_sql(
        load_sql(table, operation), execution_options=_NO_PARAMETERS_OPTION
    )


def apply_schema(session: Session) -> None:
    """Creates every missing table, in dependency order.

    Exists so an environment can be brought up from the `table.sql` files, any number of
    times; used by `main` and by the integration tests. It does not alter tables that
    already exist.

    Args:
        session: The open session whose transaction contains the migration.

    Returns:
        None: the tables are created inside the session's transaction.
    """
    for table in DatabaseTable:
        logger.info("Applying schema of table %s", table.value)
        _execute_script(session, table, SqlOperation.TABLE)


def apply_seeds(session: Session) -> None:
    """Inserts or refreshes the initial rows of the seeded tables.

    Exists so a new environment starts with its curated catalog; used by `main` and by the
    integration tests.

    Args:
        session: The open session whose transaction contains the seeds.

    Returns:
        None: the rows are written inside the session's transaction.
    """
    for table in _SEEDED_TABLES:
        logger.info("Applying seed of table %s", table.value)
        _execute_script(session, table, SqlOperation.SEED)


def main() -> None:
    """Applies the schema and the seeds to the configured database, atomically.

    Exists as the command-line entrypoint: `uv run python -m bia.database.migrate`.

    Returns:
        None: the database is updated in place.
    """
    logging.basicConfig(level=get_settings().log_level)
    with database_session(get_engine()) as session:
        apply_schema(session)
        apply_seeds(session)
    logger.info("Migration finished")


if __name__ == "__main__":
    main()
