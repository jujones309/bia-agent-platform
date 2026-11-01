from collections import defaultdict
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from bia.agents.repository import AgentNotFoundError
from bia.database.queries import DatabaseTable, SqlOperation, load_sql
from bia.tracing.artifacts import AgentMetrics, RunOrigin, RunRecord, RunStatus, RunStepRecord


class RunNotFoundError(LookupError):
    """Signals that no run has the requested identifier.

    Exists so the API can answer 404 instead of a server error. Raised by `get_run`.
    """


def list_steps_of_runs(session: Session, run_ids: list[UUID]) -> dict[UUID, list[RunStepRecord]]:
    """Lists the steps of several runs, grouped by run and in execution order.

    Exists so a run and its steps are assembled the same way everywhere with a single query;
    used by `list_runs` and by `RunRecorder.finish_run`.

    Args:
        session: The open session to read through.
        run_ids: The identifiers of the runs whose steps are wanted.

    Returns:
        dict[UUID, list[RunStepRecord]]: the steps of each run; runs without steps are absent.
    """
    sql = load_sql(DatabaseTable.RUN_STEPS, SqlOperation.LIST_BY_RUNS)
    rows = session.execute(text(sql), {"run_ids": [str(run_id) for run_id in run_ids]}).mappings()
    steps_by_run: dict[UUID, list[RunStepRecord]] = defaultdict(list)
    for row in rows:
        step = RunStepRecord.model_validate(dict(row))
        steps_by_run[step.run_id].append(step)
    return dict(steps_by_run)


def list_runs(session: Session, agent_id: UUID | None, limit: int) -> list[RunRecord]:
    """Lists the most recent runs, each with its steps.

    Exists so a person can audit what an agent did; used by the runs API.

    Args:
        session: The open session to read through.
        agent_id: The agent whose runs are wanted, or None for the runs of every agent.
        limit: The maximum number of runs to return.

    Returns:
        list[RunRecord]: the matching runs, newest first.
    """
    sql = load_sql(DatabaseTable.RUNS, SqlOperation.LIST)
    parameters = {"agent_id": str(agent_id) if agent_id else None, "limit": limit}
    runs = [
        RunRecord.model_validate(dict(row))
        for row in session.execute(text(sql), parameters).mappings()
    ]
    steps_by_run = list_steps_of_runs(session, [run.id for run in runs])
    return [run.model_copy(update={"steps": steps_by_run.get(run.id, [])}) for run in runs]


def get_run(session: Session, run_id: UUID) -> RunRecord:
    """Retrieves one run with its steps.

    Exists so the trace of a concrete answer can be opened directly, without searching the recent
    runs; used by the runs API.

    Args:
        session: The open session to read through.
        run_id: The run to look up.

    Returns:
        RunRecord: the run, with its steps in execution order.

    Raises:
        RunNotFoundError: If no run has that identifier.
    """
    sql = load_sql(DatabaseTable.RUNS, SqlOperation.GET_BY_ID)
    row = session.execute(text(sql), {"run_id": str(run_id)}).mappings().one_or_none()
    if row is None:
        raise RunNotFoundError(f"There is no run with id {run_id}")
    run = RunRecord.model_validate(dict(row))
    steps_by_run = list_steps_of_runs(session, [run.id])
    return run.model_copy(update={"steps": steps_by_run.get(run.id, [])})


def list_succeeded_runs(
    session: Session, agent_id: UUID, origin: RunOrigin, limit: int
) -> list[RunRecord]:
    """Lists the most recent runs of an agent that ended with an answer, without their steps.

    Exists as the sample of the production monitoring, which judges only the final answer; used by
    `monitor_agent`.

    Args:
        session: The open session to read through.
        agent_id: The agent whose runs are wanted.
        origin: The only origin to include.
        limit: The maximum number of runs to return.

    Returns:
        list[RunRecord]: the matching runs, newest first.
    """
    sql = load_sql(DatabaseTable.RUNS, SqlOperation.LIST_SUCCEEDED_BY_ORIGIN)
    parameters = {
        "agent_id": str(agent_id),
        "origin": origin,
        "status": RunStatus.SUCCEEDED,
        "limit": limit,
    }
    rows = session.execute(text(sql), parameters).mappings()
    return [RunRecord.model_validate(dict(row)) for row in rows]


def get_agent_metrics(
    session: Session, agent_id: UUID, origin: RunOrigin | None = None
) -> AgentMetrics:
    """Computes the run count, total cost, p50 latency and error rate of an agent.

    Exists so an agent's owner can see how it behaves in one call; used by the metrics API.
    The origin filter lets real usage be read apart from evals and the playground.

    Args:
        session: The open session to read through.
        agent_id: The agent to summarize.
        origin: The only origin to count, or None to count every origin.

    Returns:
        AgentMetrics: the aggregates; an agent without runs gets zeros and no latency or rate.

    Raises:
        AgentNotFoundError: If no agent has that identifier.
    """
    sql = load_sql(DatabaseTable.RUNS, SqlOperation.METRICS_BY_AGENT)
    parameters = {"agent_id": str(agent_id), "failed_status": RunStatus.FAILED, "origin": origin}
    row = session.execute(text(sql), parameters).mappings().one_or_none()
    if row is None:
        raise AgentNotFoundError(f"There is no agent with id {agent_id}")
    return AgentMetrics.model_validate(dict(row))
