import time
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection

from bia.database.connection import database_session
from bia.tracing.artifacts import RunOrigin, RunRecord, RunStatus, RunStepDraft, StepType
from bia.tracing.recorder import RunNotRunningError, RunRecorder
from bia.tracing.repository import list_runs
from tests.tracing.seed import insert_agent, insert_agent_version, insert_model


@pytest.fixture
def recorder(connection: Connection) -> RunRecorder:
    """Provides a recorder writing inside the test's transaction.

    Args:
        connection: The connection of the test's transaction.

    Returns:
        RunRecorder: the recorder.
    """
    return RunRecorder(connection)


@pytest.fixture
def open_run(connection: Connection, recorder: RunRecorder) -> RunRecord:
    """Provides a run that was just started for a new agent.

    Args:
        connection: The connection of the test's transaction.
        recorder: The recorder under test.

    Returns:
        RunRecord: the open run.
    """
    agent_id = insert_agent(connection)
    version_id = insert_agent_version(connection, agent_id)
    return recorder.start_run(agent_id, version_id, RunOrigin.PLAYGROUND, "¿Cuál es mi saldo?")


def _tool_step() -> RunStepDraft:
    """Builds a successful tool step without tokens.

    Returns:
        RunStepDraft: the step.
    """
    return RunStepDraft(
        step_type=StepType.TOOL_CALL, input={"numero": "1"}, output={}, latency_ms=5
    )


def _llm_step(model_id: UUID, input_tokens: int, output_tokens: int, cost: str) -> RunStepDraft:
    """Builds a successful LLM step with the given measurements.

    Args:
        model_id: The model that served the call.
        input_tokens: The input tokens of the call.
        output_tokens: The output tokens of the call.
        cost: The exact cost of the call.

    Returns:
        RunStepDraft: the step.
    """
    return RunStepDraft(
        step_type=StepType.LLM_CALL,
        model_id=model_id,
        input=[{"role": "user", "content": "hola"}],
        output="respuesta",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost=Decimal(cost),
        latency_ms=10,
    )


def test_start_opens_an_empty_running_record(open_run: RunRecord) -> None:
    """Verifies a run is visible from its start, with nothing attributed to it yet."""
    assert open_run.status is RunStatus.RUNNING
    assert open_run.input == "¿Cuál es mi saldo?"
    assert open_run.origin is RunOrigin.PLAYGROUND
    assert open_run.total_tokens == 0
    assert open_run.output is None
    assert open_run.latency_ms is None
    assert open_run.finished_at is None


def test_steps_are_numbered_from_one_within_each_run(
    recorder: RunRecorder, open_run: RunRecord
) -> None:
    """Verifies positions follow the order of the calls and do not leak across runs."""
    other_run = recorder.start_run(
        open_run.agent_id, open_run.agent_version_id, RunOrigin.EVAL, "otra"
    )

    orders = [recorder.add_step(open_run.id, _tool_step()).step_order for _ in range(2)]

    assert orders == [1, 2]
    assert recorder.add_step(other_run.id, _tool_step()).step_order == 1


def test_step_stores_its_json_documents_and_measurements(
    connection: Connection, recorder: RunRecorder, open_run: RunRecord
) -> None:
    """Verifies a conversation and a price survive the round trip without changes."""
    model_id = insert_model(connection)

    step = recorder.add_step(open_run.id, _llm_step(model_id, 7, 3, "0.00001234"))

    assert step.input == [{"role": "user", "content": "hola"}]
    assert step.output == "respuesta"
    assert step.model_id == model_id
    assert step.cost == Decimal("0.00001234")


def test_failed_step_keeps_a_null_output(recorder: RunRecorder, open_run: RunRecord) -> None:
    """Verifies a failure is stored as a SQL NULL with its message, not as a JSON null."""
    draft = RunStepDraft(step_type=StepType.TOOL_CALL, input={}, error="Sin datos", latency_ms=1)

    step = recorder.add_step(open_run.id, draft)

    assert step.output is None
    assert step.error == "Sin datos"


def test_finish_sums_tokens_and_cost_of_its_steps_exactly(
    connection: Connection, recorder: RunRecorder, open_run: RunRecord
) -> None:
    """Verifies totals come from every step, without rounding, tools contributing nothing."""
    model_id = insert_model(connection)
    recorder.add_step(open_run.id, _llm_step(model_id, 100, 20, "0.00000010"))
    recorder.add_step(open_run.id, _tool_step())
    recorder.add_step(open_run.id, _llm_step(model_id, 150, 30, "0.00000020"))

    run = recorder.finish_run(open_run.id, "Tu saldo es 100")

    assert run.status is RunStatus.SUCCEEDED
    assert run.output == "Tu saldo es 100"
    assert run.total_tokens == 300
    assert run.total_cost == Decimal("0.00000030")
    assert [step.step_order for step in run.steps] == [1, 2, 3]


def test_finish_measures_the_duration_of_the_run(
    recorder: RunRecorder, open_run: RunRecord
) -> None:
    """Verifies latency spans the real run, even when everything shares a transaction."""
    time.sleep(0.02)

    run = recorder.finish_run(open_run.id, "listo")

    assert run.latency_ms is not None
    assert run.latency_ms >= 20
    assert run.finished_at is not None
    assert run.finished_at > run.started_at


def test_a_run_opened_late_covers_the_time_already_elapsed(
    connection: Connection, recorder: RunRecorder
) -> None:
    """Verifies work done before the run could exist still counts in its duration and start."""
    agent_id = insert_agent(connection)
    version_id = insert_agent_version(connection, agent_id)

    opened = recorder.start_run(agent_id, version_id, RunOrigin.BUILDER, "texto", 5000)
    run = recorder.finish_run(opened.id, "listo")

    assert run.latency_ms is not None
    assert 5000 <= run.latency_ms < 60000
    assert run.finished_at is not None
    assert (run.finished_at - run.started_at).total_seconds() >= 5


def test_fail_stores_the_reason_and_keeps_what_was_spent(
    connection: Connection, recorder: RunRecorder, open_run: RunRecord
) -> None:
    """Verifies a failed run still accounts for the tokens it consumed."""
    recorder.add_step(open_run.id, _llm_step(insert_model(connection), 5, 5, "0.00000001"))

    run = recorder.fail_run(open_run.id, "Sin respuesta")

    assert run.status is RunStatus.FAILED
    assert run.error == "Sin respuesta"
    assert run.output is None
    assert run.total_tokens == 10
    assert run.total_cost == Decimal("0.00000001")


def test_finish_without_steps_totals_zero(recorder: RunRecorder, open_run: RunRecord) -> None:
    """Verifies a run that never reached a step closes instead of failing on NULL totals."""
    run = recorder.fail_run(open_run.id, "boom")

    assert run.total_tokens == 0
    assert run.total_cost == 0
    assert run.steps == []


def test_a_closed_run_cannot_change(
    connection: Connection, recorder: RunRecorder, open_run: RunRecord
) -> None:
    """Verifies the audit record is final: no late step or second outcome can alter it."""
    recorder.finish_run(open_run.id, "primera")

    with pytest.raises(RunNotRunningError, match=str(open_run.id)):
        recorder.add_step(open_run.id, _tool_step())
    with pytest.raises(RunNotRunningError, match=str(open_run.id)):
        recorder.fail_run(open_run.id, "tarde")

    with database_session(connection) as session:
        stored = list_runs(session, open_run.agent_id, limit=1)[0]
    assert stored.output == "primera"
    assert stored.error is None
    assert stored.status is RunStatus.SUCCEEDED
    assert stored.steps == []


def test_writes_to_an_unknown_run_fail_clearly(recorder: RunRecorder) -> None:
    """Verifies a wrong identifier is an error instead of a silently lost trace."""
    missing_id = uuid4()

    with pytest.raises(RunNotRunningError, match=str(missing_id)):
        recorder.add_step(missing_id, _tool_step())
    with pytest.raises(RunNotRunningError, match=str(missing_id)):
        recorder.finish_run(missing_id, "x")


def test_record_turn_exposes_answer_and_spending_while_the_run_stays_open(
    connection: Connection, recorder: RunRecorder, open_run: RunRecord
) -> None:
    """Verifies an abandoned conversation still reports what it answered and cost."""
    model_id = insert_model(connection)
    recorder.add_step(open_run.id, _llm_step(model_id, 10, 5, "0.001"))
    answered = recorder.record_turn(open_run.id, "Tu saldo es 100")
    recorder.add_step(open_run.id, _llm_step(model_id, 10, 5, "0.001"))

    unanswered = recorder.record_turn(open_run.id, None)

    assert answered.status is RunStatus.RUNNING
    assert unanswered.output == "Tu saldo es 100"
    assert (answered.total_tokens, unanswered.total_tokens) == (15, 30)
    assert unanswered.total_cost == Decimal("0.002")
    assert unanswered.finished_at is None


def test_finish_conversation_counts_the_time_of_the_steps_and_not_the_waiting(
    connection: Connection, recorder: RunRecorder, open_run: RunRecord
) -> None:
    """Verifies the time a person takes to reply does not inflate the latency of the agent."""
    recorder.add_step(open_run.id, _tool_step())
    recorder.record_turn(open_run.id, "Listo")
    time.sleep(0.05)

    closed = recorder.finish_conversation(open_run.id)

    assert closed.status is RunStatus.SUCCEEDED
    assert closed.error is None
    assert closed.output == "Listo"
    assert closed.latency_ms == closed.steps[0].latency_ms < 50


def test_finish_conversation_without_any_answer_fails_the_run(
    recorder: RunRecorder, open_run: RunRecord
) -> None:
    """Verifies a conversation that never got an answer counts as a failure in the metrics."""
    closed = recorder.finish_conversation(open_run.id)

    assert closed.status is RunStatus.FAILED
    assert "without any answer" in closed.error


def test_a_finished_conversation_accepts_no_more_writes(
    recorder: RunRecorder, open_run: RunRecord
) -> None:
    """Verifies a closed audit record cannot change, not even through a late turn."""
    recorder.finish_conversation(open_run.id)

    with pytest.raises(RunNotRunningError):
        recorder.record_turn(open_run.id, "tarde")
    with pytest.raises(RunNotRunningError):
        recorder.finish_conversation(open_run.id)
