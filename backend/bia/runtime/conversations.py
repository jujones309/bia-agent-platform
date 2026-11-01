import logging
from uuid import UUID

from sqlalchemy import Connection, Engine

from bia.agents.repository import get_version_by_id
from bia.database.connection import database_session
from bia.providers.factory import get_provider
from bia.runtime.artifacts import AgentRunResult
from bia.runtime.execution import AgentExecution, load_agent_execution, load_version_execution
from bia.runtime.messages import build_follow_up_messages, build_initial_messages
from bia.runtime.runner import AgentRunner
from bia.tracing.artifacts import RunOrigin, RunRecord, RunStatus
from bia.tracing.recorder import RunRecorder
from bia.tracing.repository import get_run

logger = logging.getLogger(__name__)


class ConversationNotOpenError(ValueError):
    """Signals that a run cannot receive more messages or be finished by a person.

    Exists so a finished run, or an execution that is not a conversation such as an eval in
    progress, is never altered from the playground. Raised by the functions of this module and
    translated to a 409 by `bia/api/runtime.py`.
    """


def _require_open_conversation(run: RunRecord) -> None:
    """Verifies that a run is an open conversation.

    Exists so continuing and finishing apply the same rule. Only the playground holds
    conversations; the other origins close their runs on their own.

    Args:
        run: The run about to be altered.

    Returns:
        None: the run can be altered.

    Raises:
        ConversationNotOpenError: If it is not an open conversation.
    """
    if run.origin is not RunOrigin.PLAYGROUND or run.status is not RunStatus.RUNNING:
        raise ConversationNotOpenError(f"Run {run.id} is not an open conversation")


def _build_runner(bind: Engine | Connection, execution: AgentExecution) -> AgentRunner:
    """Builds the runner of a conversation.

    Args:
        bind: The database handle to read and trace through.
        execution: The version being executed, whose model selects the provider.

    Returns:
        AgentRunner: the runner.
    """
    return AgentRunner(RunRecorder(bind), get_provider(execution.model.provider), bind)


def start_conversation(
    bind: Engine | Connection, agent_id: UUID, input_text: str
) -> AgentRunResult:
    """Opens a run with the active version of an agent and answers its first message.

    Exists as the first step of a playground conversation; used by `bia/api/runtime.py`. Reads
    happen in their own short transaction, so no connection stays open during the LLM calls.

    Args:
        bind: The database handle to read and trace through.
        agent_id: The agent to talk to.
        input_text: The first message of the user.

    Returns:
        AgentRunResult: the answer, or why there is none, with the run that stays open.

    Raises:
        ActiveVersionNotFoundError: If the agent does not exist or has no active version.
        AgentConfigurationError: If the spec references an unavailable model or tool.
    """
    with database_session(bind) as session:
        execution = load_agent_execution(session, agent_id)
    version = execution.version
    run = RunRecorder(bind).start_run(agent_id, version.id, RunOrigin.PLAYGROUND, input_text)
    messages = build_initial_messages(version.spec, input_text)
    return _build_runner(bind, execution).run_turn(run.id, execution, messages)


def continue_conversation(
    bind: Engine | Connection, agent_id: UUID, run_id: UUID, input_text: str
) -> AgentRunResult:
    """Answers a new message within an open run, remembering the earlier turns.

    Exists so a person can ask follow-up questions. It keeps the version recorded in the run, so
    the trace stays true even if the agent activates another one meanwhile; used by
    `bia/api/runtime.py`.

    Args:
        bind: The database handle to read and trace through.
        agent_id: The agent the message is addressed to.
        run_id: The open run of the conversation.
        input_text: The new message of the user.

    Returns:
        AgentRunResult: the answer, or why there is none, with the run that stays open.

    Raises:
        RunNotFoundError: If no run has that identifier.
        ConversationNotOpenError: If it is not an open conversation of that agent.
        AgentConfigurationError: If the spec references an unavailable model or tool.
    """
    with database_session(bind) as session:
        run = get_run(session, run_id)
    _require_open_conversation(run)
    if run.agent_id != agent_id:
        raise ConversationNotOpenError(f"Run {run_id} does not belong to agent {agent_id}")
    with database_session(bind) as session:
        version = get_version_by_id(session, run.agent_version_id)
        execution = load_version_execution(session, version)
    messages = build_follow_up_messages(version.spec, run.steps, input_text)
    logger.info("Continuing conversation %s with %d messages", run_id, len(messages))
    return _build_runner(bind, execution).run_turn(run_id, execution, messages)


def finish_conversation(bind: Engine | Connection, run_id: UUID) -> RunRecord:
    """Closes an open conversation, after which the agent starts over in a new run.

    Exists so a person decides when a conversation ends; used by `bia/api/runtime.py`.

    Args:
        bind: The database handle to read and trace through.
        run_id: The conversation to finish.

    Returns:
        RunRecord: the closed run, with its totals and its steps.

    Raises:
        RunNotFoundError: If no run has that identifier.
        ConversationNotOpenError: If it is not an open conversation.
    """
    with database_session(bind) as session:
        run = get_run(session, run_id)
    _require_open_conversation(run)
    return RunRecorder(bind).finish_conversation(run_id)
