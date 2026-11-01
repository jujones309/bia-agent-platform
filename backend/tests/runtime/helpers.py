from uuid import UUID

from sqlalchemy import Connection

from bia.database.connection import database_session
from bia.providers.base import ModelProvider
from bia.runtime.artifacts import AgentRunResult
from bia.runtime.execution import load_agent_execution
from bia.runtime.runner import AgentRunner
from bia.tracing.artifacts import RunOrigin
from bia.tracing.recorder import RunRecorder


def run_once(
    connection: Connection,
    provider: ModelProvider,
    agent_id: UUID,
    input_text: str,
    origin: RunOrigin,
) -> AgentRunResult:
    """Executes the active version of an agent in a run that closes on its own.

    Exists so integration tests can produce closed runs of any origin in one line.

    Args:
        connection: The connection of the test's transaction.
        provider: The scripted provider.
        agent_id: The agent to execute.
        input_text: What the user asked.
        origin: What triggered the execution.

    Returns:
        AgentRunResult: the outcome of the run.
    """
    with database_session(connection) as session:
        execution = load_agent_execution(session, agent_id)
    runner = AgentRunner(RunRecorder(connection), provider, connection)
    return runner.run(execution, input_text, origin)
