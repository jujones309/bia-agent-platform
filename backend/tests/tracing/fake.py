from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from bia.tracing.artifacts import RunOrigin, RunRecord, RunStatus, RunStepDraft, RunStepRecord
from bia.tracing.recorder import RunRecorder


class FakeRunRecorder(RunRecorder):
    """Replaces the database in tests of code that records runs.

    Exists so the runtime's loop is tested on every test run, including CI, where there is
    no Postgres. Lives under `tests/`; the real SQL is covered by `test_recorder.py`.
    """

    def __init__(self) -> None:
        """Starts without runs; deliberately opens no database handle."""
        self.run: RunRecord | None = None
        self.steps: list[RunStepDraft] = []

    def start_run(
        self, agent_id: UUID, agent_version_id: UUID, origin: RunOrigin, input_text: str
    ) -> RunRecord:
        """Keeps a new open run.

        Args:
            agent_id: The agent being executed.
            agent_version_id: The version being executed.
            origin: What triggered the execution.
            input_text: The input the agent received.

        Returns:
            RunRecord: the open run.
        """
        self.run = RunRecord(
            id=uuid4(),
            agent_id=agent_id,
            agent_version_id=agent_version_id,
            origin=origin,
            input=input_text,
            output=None,
            status=RunStatus.RUNNING,
            error=None,
            total_tokens=0,
            total_cost=Decimal(0),
            latency_ms=None,
            started_at=datetime.now(UTC),
            finished_at=None,
        )
        return self.run

    def add_step(self, run_id: UUID, step: RunStepDraft) -> RunStepRecord:
        """Keeps a step.

        Args:
            run_id: The run the step belongs to.
            step: What happened in the step.

        Returns:
            RunStepRecord: the step with its position.
        """
        self.steps.append(step)
        return RunStepRecord(
            id=uuid4(),
            run_id=run_id,
            step_order=len(self.steps),
            created_at=datetime.now(UTC),
            **step.model_dump(),
        )

    def _close_run(
        self, run_id: UUID, status: RunStatus, output: str | None, error: str | None
    ) -> RunRecord:
        """Closes the kept run; reached through the real `finish_run` and `fail_run`.

        Args:
            run_id: The run to close.
            status: The final status.
            output: The final answer, if it succeeded.
            error: The reason, if it failed.

        Returns:
            RunRecord: the closed run.

        Raises:
            AssertionError: If the code under test closes a run twice.
        """
        assert self.run is not None and self.run.status is RunStatus.RUNNING, "Run closed twice"
        self.run = self.run.model_copy(update={"status": status, "output": output, "error": error})
        return self.run
