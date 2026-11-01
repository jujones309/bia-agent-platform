import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from bia.agents.artifacts import AgentKind, AgentStatus
from bia.builder.artifacts import DuplicateCandidate
from bia.database.queries import DatabaseTable, SqlOperation, load_sql

_MAX_CANDIDATES = 3


def find_candidates(session: Session, embedding: list[float]) -> list[DuplicateCandidate]:
    """Finds the published agents of employees closest to a need.

    Exists to narrow the registry down to what the judge can compare; used by `check_duplicates`.
    It applies no similarity threshold, because deciding what is close enough is the judge's job.

    Args:
        session: The open session to read through.
        embedding: The vector of the described need.

    Returns:
        list[DuplicateCandidate]: at most three agents, closest first.
    """
    parameters = {
        "query_embedding": json.dumps(embedding),
        "status": AgentStatus.PUBLISHED,
        "kind": AgentKind.USER,
        "limit": _MAX_CANDIDATES,
    }
    sql = load_sql(DatabaseTable.AGENTS, SqlOperation.SEARCH_BY_EMBEDDING)
    rows = session.execute(text(sql), parameters).mappings()
    return [DuplicateCandidate.model_validate(dict(row)) for row in rows]
