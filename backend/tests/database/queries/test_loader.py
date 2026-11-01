import re

import pytest

from bia.database.queries import DatabaseTable, SqlFileNotFoundError, SqlOperation, load_sql

_REFERENCED_TABLE = re.compile(r"REFERENCES (\w+)")
_COLUMN_LINE = re.compile(r"^    (?!UNIQUE\b)\w+ .+$")
_TABLES_WITH_INDEX = {DatabaseTable.KNOWLEDGE_CHUNKS}  # each one requested explicitly


def test_load_sql_reads_the_file_of_the_requested_table() -> None:
    """Verifies the table and operation select the right file, not just any SQL."""
    assert "CREATE TABLE IF NOT EXISTS run_steps" in load_sql(
        DatabaseTable.RUN_STEPS, SqlOperation.TABLE
    )


def test_load_sql_names_table_and_operation_when_file_is_missing() -> None:
    """Verifies a missing file fails saying which table and operation were requested."""
    with pytest.raises(SqlFileNotFoundError, match="'runs' has no 'seed'"):
        load_sql(DatabaseTable.RUNS, SqlOperation.SEED)


@pytest.mark.parametrize("table", list(DatabaseTable))
def test_table_file_follows_the_schema_conventions(table: DatabaseTable) -> None:
    """Verifies each schema is documented, idempotent, closed to the API, with no unasked index."""
    sql = load_sql(table, SqlOperation.TABLE)

    assert sql.startswith("-- ")
    assert f"CREATE TABLE IF NOT EXISTS {table} (" in sql
    assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;" in sql
    assert ("CREATE INDEX" in sql.upper()) is (table in _TABLES_WITH_INDEX)


@pytest.mark.parametrize("table", list(DatabaseTable))
def test_every_column_has_a_comment_above_it(table: DatabaseTable) -> None:
    """Verifies no column is left without its documentation line."""
    lines = load_sql(table, SqlOperation.TABLE).splitlines()

    undocumented = [
        line
        for previous, line in zip(lines, lines[1:], strict=False)
        if _COLUMN_LINE.match(line) and not previous.lstrip().startswith("--")
    ]

    assert undocumented == []


def test_tables_are_declared_after_the_tables_they_reference() -> None:
    """Verifies the enum order works as migration order, which a bad order would break."""
    declared = list(DatabaseTable)

    for position, table in enumerate(declared):
        referenced = _REFERENCED_TABLE.findall(load_sql(table, SqlOperation.TABLE))
        assert set(referenced) <= set(declared[:position]), f"{table} references a later table"
