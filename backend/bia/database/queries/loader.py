from enum import StrEnum
from pathlib import Path

_QUERIES_DIRECTORY = Path(__file__).resolve().parent
_SQL_SUFFIX = ".sql"


class DatabaseTable(StrEnum):
    """The tables of the platform, declared in dependency order.

    Exists so SQL files are addressed through a closed set, and because the declaration
    order is the order in which `bia/database/migrate.py` creates them: a table must
    appear after every table it references. Consumed by `load_sql` and the migration.
    """

    MODELS = "models"
    TOOLS = "tools"
    AGENTS = "agents"
    AGENT_VERSIONS = "agent_versions"
    KNOWLEDGE_BASES = "knowledge_bases"
    KNOWLEDGE_DOCUMENTS = "knowledge_documents"
    KNOWLEDGE_CHUNKS = "knowledge_chunks"
    RUNS = "runs"
    RUN_STEPS = "run_steps"
    EVAL_CASES = "eval_cases"
    EVAL_RESULTS = "eval_results"
    ORCHESTRATIONS = "orchestrations"
    ORCHESTRATION_STEPS = "orchestration_steps"


class SqlOperation(StrEnum):
    """The SQL files a table directory can hold, named after the file they map to.

    Exists so callers cannot misspell a file name; consumed by `load_sql`. Each vertical
    adds its operations here as it needs them.
    """

    TABLE = "table"  # the table's schema DDL
    SEED = "seed"  # the table's idempotent initial rows
    LIST = "list"
    GET_BY_ID = "get_by_id"
    UPSERT = "upsert"
    DEACTIVATE_EXCEPT = "deactivate_except"
    INSERT = "insert"
    FINISH = "finish"
    LIST_BY_RUNS = "list_by_runs"
    METRICS_BY_AGENT = "metrics_by_agent"
    GET_ACTIVE = "get_active"
    LOCK_BY_ID = "lock_by_id"
    SET_ACTIVE_VERSION = "set_active_version"
    LIST_BY_AGENT = "list_by_agent"
    GET_BY_NUMBER = "get_by_number"
    DELETE_BY_DOCUMENT = "delete_by_document"
    SEARCH_BY_EMBEDDING = "search_by_embedding"
    SET_STATUS = "set_status"
    LIST_LATEST_BY_VERSION = "list_latest_by_version"
    LIST_SUCCEEDED_BY_ORIGIN = "list_succeeded_by_origin"
    INVENTORY = "inventory"
    COST_OF_CURRENT_MONTH = "cost_of_current_month"
    DELETE_BY_ORCHESTRATION = "delete_by_orchestration"
    RETIRE = "retire"  # hides a row from the current reads, keeping it as history
    RENAME = "rename"
    EXISTS_BY_AGENT = "exists_by_agent"
    UPDATE_IDENTITY = "update_identity"
    LIST_BY_BASE = "list_by_base"


class SqlFileNotFoundError(FileNotFoundError):
    """Signals that a table does not have the requested SQL file.

    Exists to name the missing table and operation instead of a bare path. Raised by
    `load_sql`.
    """


def load_sql(table: DatabaseTable, operation: SqlOperation) -> str:
    """Reads the SQL statement of a table's operation.

    Exists because SQL lives in `.sql` files and never in Python strings; used by every
    vertical that talks to the database.

    Args:
        table: The table whose directory holds the file.
        operation: The operation that names the file.

    Returns:
        str: the content of the SQL file.

    Raises:
        SqlFileNotFoundError: If the table has no file for that operation.
    """
    path = _QUERIES_DIRECTORY / table / f"{operation}{_SQL_SUFFIX}"
    if not path.is_file():
        raise SqlFileNotFoundError(f"Table '{table}' has no '{operation}' SQL file at {path}")
    return path.read_text(encoding="utf-8")
