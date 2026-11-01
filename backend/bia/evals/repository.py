from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from bia.database.queries import DatabaseTable, SqlOperation, load_sql
from bia.evals.artifacts import (
    EvalCase,
    EvalCaseDraft,
    EvalCaseOrigin,
    EvalJudgement,
    EvalResult,
)


class EvalCaseNotFoundError(LookupError):
    """Signals that an agent has no current case with the requested identifier.

    Exists so retiring a wrong or already retired case fails clearly. Raised by `retire_case` and
    translated to a 404 by `bia/api/evals.py`.
    """


def insert_case(
    session: Session, agent_id: UUID, draft: EvalCaseDraft, origin: EvalCaseOrigin
) -> EvalCase:
    """Stores a test case of an agent.

    Exists as the single write of cases, generated or manual; used by `bia/evals/cases.py`.

    Args:
        session: The open session whose transaction contains the write.
        agent_id: The agent the case evaluates.
        draft: What to ask and what to expect.
        origin: How the case was created.

    Returns:
        EvalCase: the stored case.
    """
    parameters = {
        "agent_id": str(agent_id),
        "input": draft.input,
        "expected_behavior": draft.expected_behavior,
        "origin": origin,
    }
    sql = load_sql(DatabaseTable.EVAL_CASES, SqlOperation.INSERT)
    return EvalCase.model_validate(dict(session.execute(text(sql), parameters).mappings().one()))


def list_cases(session: Session, agent_id: UUID) -> list[EvalCase]:
    """Lists the current test cases of an agent, oldest first.

    Exists because every eval run and report covers all of them, and retired ones no longer count;
    used across `bia/evals/`.

    Args:
        session: The open session to read through.
        agent_id: The agent to look up.

    Returns:
        list[EvalCase]: its cases; empty if it has none.
    """
    sql = load_sql(DatabaseTable.EVAL_CASES, SqlOperation.LIST_BY_AGENT)
    rows = session.execute(text(sql), {"agent_id": str(agent_id)}).mappings()
    return [EvalCase.model_validate(dict(row)) for row in rows]


def retire_case(session: Session, agent_id: UUID, eval_case_id: UUID) -> None:
    """Takes a case out of the reports and the gate, keeping its row and its results.

    Exists because the results of a case are the audit record of past decisions of the gate, so the
    row cannot be deleted; used by `remove_case`.

    Args:
        session: The open session whose transaction contains the write.
        agent_id: The agent the case must belong to.
        eval_case_id: The case to retire.

    Returns:
        None: the case is retired inside the session's transaction.

    Raises:
        EvalCaseNotFoundError: If the agent has no current case with that identifier.
    """
    parameters = {"agent_id": str(agent_id), "eval_case_id": str(eval_case_id)}
    sql = load_sql(DatabaseTable.EVAL_CASES, SqlOperation.RETIRE)
    if session.execute(text(sql), parameters).one_or_none() is None:
        raise EvalCaseNotFoundError(f"Agent {agent_id} has no current case {eval_case_id}")


def insert_result(
    session: Session,
    eval_case_id: UUID,
    agent_version_id: UUID,
    output: str,
    judgement: EvalJudgement,
) -> EvalResult:
    """Stores the outcome of evaluating one case against one version.

    Exists as the single write of results; used by `run_evals`.

    Args:
        session: The open session whose transaction contains the write.
        eval_case_id: The case evaluated.
        agent_version_id: The version evaluated.
        output: The agent's answer; empty if it produced none.
        judgement: The decision on that answer.

    Returns:
        EvalResult: the stored result.
    """
    parameters = {
        "eval_case_id": str(eval_case_id),
        "agent_version_id": str(agent_version_id),
        "output": output,
        "verdict": judgement.verdict,
        "score": judgement.score,
        "judge_reason": judgement.reason,
    }
    sql = load_sql(DatabaseTable.EVAL_RESULTS, SqlOperation.INSERT)
    return EvalResult.model_validate(dict(session.execute(text(sql), parameters).mappings().one()))


def list_latest_results(session: Session, agent_version_id: UUID) -> dict[UUID, EvalResult]:
    """Finds the most recent result of each case on one version.

    Exists because the gate reads only the latest run of a case, and older results stay as history;
    used by `build_report`.

    Args:
        session: The open session to read through.
        agent_version_id: The version to look up.

    Returns:
        dict[UUID, EvalResult]: the result of each evaluated case, by case identifier.
    """
    sql = load_sql(DatabaseTable.EVAL_RESULTS, SqlOperation.LIST_LATEST_BY_VERSION)
    rows = session.execute(text(sql), {"agent_version_id": str(agent_version_id)}).mappings()
    results = [EvalResult.model_validate(dict(row)) for row in rows]
    return {result.eval_case_id: result for result in results}
