from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection

from bia.database.connection import database_session
from bia.tracing.artifacts import RunOrigin, RunStatus, RunStepDraft, StepType
from bia.tracing.recorder import RunRecorder
from bia.tracing.repository import AgentNotFoundError, get_agent_metrics, list_runs
from tests.tracing.seed import insert_agent, insert_agent_version, insert_finished_run


def _new_agent(connection: Connection) -> tuple[UUID, UUID]:
    """Creates an agent with its first version.

    Args:
        connection: The connection of the test's transaction.

    Returns:
        tuple[UUID, UUID]: the identifiers of the agent and of the version.
    """
    agent_id = insert_agent(connection)
    return agent_id, insert_agent_version(connection, agent_id)


def _tool_step(marker: str) -> RunStepDraft:
    """Builds a tool step recognizable by its input.

    Args:
        marker: The value that identifies the step.

    Returns:
        RunStepDraft: the step.
    """
    return RunStepDraft(
        step_type=StepType.TOOL_CALL, input={"marker": marker}, output={}, latency_ms=1
    )


def test_list_filters_by_agent_and_attaches_each_run_its_own_steps(connection: Connection) -> None:
    """Verifies runs never show another agent's activity or another run's steps."""
    recorder = RunRecorder(connection)
    agent_id, version_id = _new_agent(connection)
    other_agent_id, other_version_id = _new_agent(connection)
    run = recorder.start_run(agent_id, version_id, RunOrigin.PLAYGROUND, "mine")
    other = recorder.start_run(other_agent_id, other_version_id, RunOrigin.PLAYGROUND, "other")
    recorder.add_step(run.id, _tool_step("first"))
    recorder.add_step(run.id, _tool_step("second"))
    recorder.add_step(other.id, _tool_step("foreign"))

    with database_session(connection) as session:
        runs = list_runs(session, agent_id, limit=10)

    assert [listed.id for listed in runs] == [run.id]
    assert [step.input for step in runs[0].steps] == [{"marker": "first"}, {"marker": "second"}]


def test_list_without_agent_returns_newest_first_within_the_limit(connection: Connection) -> None:
    """Verifies the unfiltered view spans agents, and the cap keeps the most recent runs."""
    recorder = RunRecorder(connection)
    agent_id, version_id = _new_agent(connection)
    other_agent_id, other_version_id = _new_agent(connection)
    recorder.start_run(agent_id, version_id, RunOrigin.PLAYGROUND, "oldest")
    middle = recorder.start_run(other_agent_id, other_version_id, RunOrigin.EVAL, "middle")
    newest = recorder.start_run(agent_id, version_id, RunOrigin.PLAYGROUND, "newest")

    with database_session(connection) as session:
        runs = list_runs(session, None, limit=2)

    assert [run.id for run in runs] == [newest.id, middle.id]


def test_list_returns_a_run_without_steps_with_an_empty_list(connection: Connection) -> None:
    """Verifies a run that has not reached a step is still listed."""
    agent_id, version_id = _new_agent(connection)
    RunRecorder(connection).start_run(agent_id, version_id, RunOrigin.PLAYGROUND, "x")

    with database_session(connection) as session:
        runs = list_runs(session, agent_id, limit=10)

    assert runs[0].steps == []


def test_metrics_aggregate_only_the_runs_of_the_agent(connection: Connection) -> None:
    """Verifies each aggregate against known runs, with a running run and a foreign one."""
    agent_id, version_id = _new_agent(connection)
    other_agent_id, other_version_id = _new_agent(connection)
    for status, latency_ms, cost in (
        (RunStatus.SUCCEEDED, 100, "0.10"),
        (RunStatus.SUCCEEDED, 200, "0.20"),
        (RunStatus.FAILED, 900, "0.05"),
    ):
        insert_finished_run(connection, agent_id, version_id, status, latency_ms, Decimal(cost))
    insert_finished_run(
        connection, other_agent_id, other_version_id, RunStatus.FAILED, 5000, Decimal("9")
    )
    RunRecorder(connection).start_run(agent_id, version_id, RunOrigin.PLAYGROUND, "in progress")

    with database_session(connection) as session:
        metrics = get_agent_metrics(session, agent_id)

    assert metrics.total_runs == 4
    assert metrics.total_cost == Decimal("0.35")
    assert metrics.latency_p50_ms == 200
    assert metrics.error_rate == pytest.approx(1 / 3)


def test_metrics_of_an_agent_without_runs_have_no_latency_or_rate(connection: Connection) -> None:
    """Verifies a new agent gets zeros instead of a division by zero or a 404."""
    agent_id, _ = _new_agent(connection)

    with database_session(connection) as session:
        metrics = get_agent_metrics(session, agent_id)

    assert metrics.total_runs == 0
    assert metrics.total_cost == 0
    assert metrics.latency_p50_ms is None
    assert metrics.error_rate is None


def test_metrics_of_an_agent_with_only_running_runs_have_no_rate(connection: Connection) -> None:
    """Verifies an unfinished run counts as activity without skewing the rate."""
    agent_id, version_id = _new_agent(connection)
    RunRecorder(connection).start_run(agent_id, version_id, RunOrigin.PLAYGROUND, "x")

    with database_session(connection) as session:
        metrics = get_agent_metrics(session, agent_id)

    assert metrics.total_runs == 1
    assert metrics.error_rate is None


def test_metrics_of_an_unknown_agent_fail_clearly(connection: Connection) -> None:
    """Verifies a wrong identifier is told apart from an agent without runs."""
    missing_id = uuid4()

    with (
        database_session(connection) as session,
        pytest.raises(AgentNotFoundError, match=str(missing_id)),
    ):
        get_agent_metrics(session, missing_id)
