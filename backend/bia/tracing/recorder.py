import json
import logging
from uuid import UUID

from sqlalchemy import Connection, Engine, text
from sqlalchemy.engine import RowMapping

from bia.database.connection import database_session
from bia.database.queries import DatabaseTable, SqlOperation, load_sql
from bia.tracing.artifacts import (
    RunOrigin,
    RunRecord,
    RunStatus,
    RunStepDraft,
    RunStepRecord,
)
from bia.tracing.repository import list_steps_of_runs

logger = logging.getLogger(__name__)


class RunNotRunningError(LookupError):
    """Signals a write to a run that does not exist or was already closed.

    Exists so a closed audit record can never change silently, and so a wrong identifier
    fails close to the source. Raised by the write methods of `RunRecorder`.
    """


class RunRecorder:
    """Writes the audit record of an execution while it happens.

    Exists so the runtime, the builder and the evals record runs the same way. Every write
    commits on its own, on purpose: a run that crashes must leave its trace behind, which
    would be lost if the trace shared the transaction of the failing work. Consumed by
    `bia/runtime/`, `bia/builder/` and `bia/evals/`.
    """

    def __init__(self, bind: Engine | Connection) -> None:
        """Creates a recorder that writes through the given database handle.

        Args:
            bind (Engine | Connection): Where each write opens its own session. Production
                passes the engine; a connection lets tests wrap everything in one transaction.
        """
        self._bind = bind

    def start_run(
        self,
        agent_id: UUID,
        agent_version_id: UUID,
        origin: RunOrigin,
        input_text: str,
        already_elapsed_ms: int = 0,
    ) -> RunRecord:
        """Opens the record of an execution in the running state.

        Exists so a run is visible from its first moment, even if it never finishes; called
        before the first step of an execution.

        Args:
            agent_id: The agent being executed.
            agent_version_id: The exact version being executed.
            origin: What triggered the execution.
            input_text: The input the agent received.
            already_elapsed_ms: How long the execution has been going on, for work that had to
                happen before its run could exist, so the run's duration still covers it.

        Returns:
            RunRecord: the open run, whose `id` the following calls need.
        """
        parameters = {
            "agent_id": str(agent_id),
            "agent_version_id": str(agent_version_id),
            "origin": origin,
            "input": input_text,
            "status": RunStatus.RUNNING,
            "already_elapsed_ms": already_elapsed_ms,
        }
        with database_session(self._bind) as session:
            sql = load_sql(DatabaseTable.RUNS, SqlOperation.INSERT)
            row = session.execute(text(sql), parameters).mappings().one()
        run = RunRecord.model_validate(dict(row))
        logger.info("Run %s started for agent %s (%s)", run.id, agent_id, origin.value)
        return run

    def add_step(self, run_id: UUID, step: RunStepDraft) -> RunStepRecord:
        """Appends a step to an open run, at the next position.

        Exists to record each model call, tool call and retrieval as soon as it ends; called
        once per step. Steps of one run must be added sequentially.

        Args:
            run_id: The run the step belongs to.
            step: What happened in the step.

        Returns:
            RunStepRecord: the stored step, with its position.

        Raises:
            RunNotRunningError: If the run does not exist or was already closed.
        """
        with database_session(self._bind) as session:
            sql = load_sql(DatabaseTable.RUN_STEPS, SqlOperation.INSERT)
            row = session.execute(text(sql), _step_parameters(run_id, step)).mappings().first()
        record = RunStepRecord.model_validate(dict(_require_open_run(row, run_id)))
        logger.info(
            "Run %s recorded step %d (%s)", run_id, record.step_order, record.step_type.value
        )
        return record

    def finish_run(self, run_id: UUID, output: str) -> RunRecord:
        """Closes an open run as succeeded, summing the tokens and cost of its steps.

        Exists so totals always come from the recorded steps and cannot disagree with them;
        called once at the end of a successful execution.

        Args:
            run_id: The run to close.
            output: The final answer.

        Returns:
            RunRecord: the closed run, with its totals and its steps.

        Raises:
            RunNotRunningError: If the run does not exist or was already closed.
        """
        return self._close_run(run_id, RunStatus.SUCCEEDED, output, None)

    def fail_run(self, run_id: UUID, error: str) -> RunRecord:
        """Closes an open run as failed, keeping the reason and what it already spent.

        Exists because some failures, such as reaching the iteration limit, belong to no
        step; called once when an execution cannot produce an answer.

        Args:
            run_id: The run to close.
            error: Why the run failed.

        Returns:
            RunRecord: the closed run, with its totals and its steps.

        Raises:
            RunNotRunningError: If the run does not exist or was already closed.
        """
        return self._close_run(run_id, RunStatus.FAILED, None, error)

    def _close_run(
        self, run_id: UUID, status: RunStatus, output: str | None, error: str | None
    ) -> RunRecord:
        """Writes the outcome of a run and reads back its totals and steps.

        Exists as the shared write of `finish_run` and `fail_run`.

        Args:
            run_id: The run to close.
            status: The final status.
            output: The final answer, if it succeeded.
            error: The reason, if it failed.

        Returns:
            RunRecord: the closed run, with its totals and its steps.

        Raises:
            RunNotRunningError: If the run does not exist or was already closed.
        """
        parameters = {
            "run_id": str(run_id),
            "output": output,
            "status": status,
            "error": error,
            "running_status": RunStatus.RUNNING,
        }
        with database_session(self._bind) as session:
            sql = load_sql(DatabaseTable.RUNS, SqlOperation.FINISH)
            row = session.execute(text(sql), parameters).mappings().first()
            steps = list_steps_of_runs(session, [run_id]).get(run_id, [])
        run = RunRecord.model_validate({**_require_open_run(row, run_id), "steps": steps})
        logger.info(
            "Run %s finished as %s in %s ms, %d tokens, cost $%s",
            run.id,
            run.status.value,
            run.latency_ms,
            run.total_tokens,
            run.total_cost,
        )
        return run


def _step_parameters(run_id: UUID, step: RunStepDraft) -> dict[str, object]:
    """Builds the bound parameters of the step insert.

    Exists to keep the translation to column values apart from the write; used by
    `RunRecorder.add_step`. An absent output stays NULL instead of the JSON value `null`.

    Args:
        run_id: The run the step belongs to.
        step: The validated step.

    Returns:
        dict[str, object]: the parameters of `run_steps/insert.sql`.
    """
    return {
        "run_id": str(run_id),
        "running_status": RunStatus.RUNNING,
        "step_type": step.step_type,
        "model_id": str(step.model_id) if step.model_id else None,
        "tool_id": str(step.tool_id) if step.tool_id else None,
        "input": json.dumps(step.input),
        "output": None if step.output is None else json.dumps(step.output),
        "input_tokens": step.input_tokens,
        "output_tokens": step.output_tokens,
        "cost": step.cost,
        "latency_ms": step.latency_ms,
        "error": step.error,
    }


def _require_open_run(row: RowMapping | None, run_id: UUID) -> RowMapping:
    """Verifies that a conditional write on an open run actually matched it.

    Exists because the write queries return no row for a missing or closed run; used by
    `RunRecorder.add_step` and `RunRecorder._close_run`, after their session ended, so the
    failure does not roll back anything that was already recorded.

    Args:
        row: The row returned by the write, if any.
        run_id: The run the write targeted.

    Returns:
        RowMapping: the row that was written.

    Raises:
        RunNotRunningError: If the write matched no row.
    """
    if row is None:
        raise RunNotRunningError(f"There is no running run with id {run_id}")
    return row
