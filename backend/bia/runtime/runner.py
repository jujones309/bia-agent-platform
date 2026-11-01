import logging
import time
from uuid import UUID

from sqlalchemy import Connection, Engine

from bia.catalog.tools.base import ToolContext
from bia.providers.artifacts import ChatMessage, ToolCall
from bia.providers.base import ModelProvider, ProviderError
from bia.providers.cost import compute_cost
from bia.runtime.artifacts import AgentRunResult
from bia.runtime.execution import AgentExecution
from bia.runtime.messages import build_initial_messages
from bia.runtime.tools import ToolExecutor, to_tool_message
from bia.tracing.artifacts import RunOrigin, RunRecord, RunStepDraft, StepType
from bia.tracing.recorder import RunRecorder

logger = logging.getLogger(__name__)

_MILLISECONDS_PER_SECOND = 1000


class IterationLimitError(RuntimeError):
    """Signals that the loop reached the iteration limit of a spec without an answer.

    Exists so each kind of execution decides what that means for its run; raised by
    `AgentRunner._run_loop` and handled by `AgentRunner.run` and `AgentRunner.run_turn`.
    """


def elapsed_ms(started_at: float) -> int:
    """Measures the milliseconds since a `time.perf_counter` reading.

    Exists so model failures and tool calls, which report no latency, are measured alike; used
    by the runner and by the system agents of the builder.

    Args:
        started_at: The earlier reading.

    Returns:
        int: the elapsed whole milliseconds.
    """
    return int((time.perf_counter() - started_at) * _MILLISECONDS_PER_SECOND)


def _to_result(run: RunRecord) -> AgentRunResult:
    """Reduces a closed run to what the caller of an execution needs.

    Args:
        run: The closed run.

    Returns:
        AgentRunResult: the outcome and the identifier of its trace.
    """
    return AgentRunResult(run_id=run.id, status=run.status, output=run.output, error=run.error)


def _dump_messages(messages: list[ChatMessage]) -> list[dict[str, object]]:
    """Converts a conversation to the JSON stored in the trace of a model call.

    Args:
        messages: The conversation sent to the model.

    Returns:
        list[dict[str, object]]: the JSON-compatible messages.
    """
    return [message.model_dump(mode="json") for message in messages]


class AgentRunner:
    """Executes any agent version: the generic tool-calling loop of the platform.

    Exists so agents are configuration and only one piece of code runs them. It guarantees
    that every run ends closed, whatever happens, and that each model call and tool call is
    recorded. Consumed by `bia/runtime/conversations.py` for the playground and by the evals.
    """

    def __init__(
        self, recorder: RunRecorder, provider: ModelProvider, bind: Engine | Connection
    ) -> None:
        """Creates a runner.

        Args:
            recorder (RunRecorder): Where the trace of each execution is written.
            provider (ModelProvider): The door to the model of the execution.
            bind (Engine | Connection): The database handle the tools read through.
        """
        self._recorder = recorder
        self._provider = provider
        self._bind = bind

    def run(self, execution: AgentExecution, input_text: str, origin: RunOrigin) -> AgentRunResult:
        """Executes an agent from start to finish, leaving its run closed.

        Exists as the entrypoint of executions with a single input, such as the evals. A provider
        failure is a normal outcome reported in the result. Anything else is a bug: the run is
        closed and it propagates.

        Args:
            execution: The version to execute, with its model and tools.
            input_text: What the user asked.
            origin: What triggered the execution.

        Returns:
            AgentRunResult: the answer, or why there is none, with the run identifier.
        """
        version = execution.version
        run = self._recorder.start_run(version.agent_id, version.id, origin, input_text)
        messages = build_initial_messages(version.spec, input_text)
        try:
            output = self._run_loop(run.id, execution, messages)
            return _to_result(self._recorder.finish_run(run.id, output))
        except (ProviderError, IterationLimitError) as error:
            logger.warning("Run %s failed: %s", run.id, error)
            return _to_result(self._recorder.fail_run(run.id, str(error)))
        except Exception as error:
            self._fail_crashed_run(run.id, error)
            raise

    def run_turn(
        self, run_id: UUID, execution: AgentExecution, messages: list[ChatMessage]
    ) -> AgentRunResult:
        """Executes one turn of a conversation, leaving its run open.

        Exists because a conversation outlives each answer. A turn without an answer does not end
        it: the person can try again, and the error step stays in the trace. Anything else is a
        bug: the run is closed and it propagates. Used by `bia/runtime/conversations.py`.

        Args:
            run_id: The open run of the conversation.
            execution: The version the conversation executes, with its model and tools.
            messages: The conversation so far, ending with the new user message.

        Returns:
            AgentRunResult: the answer of the turn, or why there is none, with the run identifier.
        """
        try:
            output = self._run_loop(run_id, execution, messages)
            return _to_result(self._recorder.record_turn(run_id, output))
        except (ProviderError, IterationLimitError) as error:
            logger.warning("Run %s had a turn without an answer: %s", run_id, error)
            run = self._recorder.record_turn(run_id, None)
            return AgentRunResult(run_id=run.id, status=run.status, output=None, error=str(error))
        except Exception as error:
            self._fail_crashed_run(run_id, error)
            raise

    def _fail_crashed_run(self, run_id: UUID, error: Exception) -> None:
        """Closes a run after an unexpected error, for the caller to let it propagate.

        Exists so no run stays open because of a bug; used by `run` and `run_turn`.

        Args:
            run_id: The open run.
            error: The unexpected error.

        Returns:
            None: the run ends up closed as failed.
        """
        logger.exception("Run %s crashed", run_id)
        self._recorder.fail_run(run_id, f"{type(error).__name__}: {error}")

    def _run_loop(
        self, run_id: UUID, execution: AgentExecution, messages: list[ChatMessage]
    ) -> str:
        """Alternates model calls and tool calls until an answer or the iteration limit.

        Exists to keep the loop apart from how each kind of execution ends its run.

        Args:
            run_id: The open run.
            execution: The version to execute, with its model and tools.
            messages: The conversation so far; it grows as the loop advances.

        Returns:
            str: the answer of the model.

        Raises:
            ProviderError: If a model call fails.
            IterationLimitError: If the limit is reached without an answer.
        """
        spec = execution.version.spec
        context = ToolContext(bind=self._bind, knowledge_base_id=spec.knowledge_base_id)
        executor = ToolExecutor(execution.tools, context)
        for _ in range(spec.max_iterations):
            reply = self._call_model(run_id, execution, messages, executor)
            messages.append(reply)
            if not reply.tool_calls:
                return reply.content
            for tool_call in reply.tool_calls:
                messages.append(self._call_tool(run_id, executor, tool_call))
        raise IterationLimitError(
            f"Reached the limit of {spec.max_iterations} iterations without an answer"
        )

    def _call_model(
        self,
        run_id: UUID,
        execution: AgentExecution,
        messages: list[ChatMessage],
        executor: ToolExecutor,
    ) -> ChatMessage:
        """Calls the model and records the call, whether it worked or not.

        Exists so no model call escapes the trace, not even a failed one.

        Args:
            run_id: The open run.
            execution: The version being executed.
            messages: The conversation so far.
            executor: The source of the tools offered.

        Returns:
            ChatMessage: the model's reply; has text or tool calls, per the provider contract.

        Raises:
            ProviderError: If the call fails, after recording it.
        """
        model = execution.model
        started_at = time.perf_counter()
        step = {"model_id": model.id, "input": _dump_messages(messages)}
        try:
            result = self._provider.chat(
                messages, model.provider_model_id, executor.definitions() or None
            )
        except ProviderError as error:
            self._recorder.add_step(
                run_id,
                RunStepDraft(
                    step_type=StepType.LLM_CALL,
                    error=str(error),
                    latency_ms=elapsed_ms(started_at),
                    **step,
                ),
            )
            raise
        self._recorder.add_step(
            run_id,
            RunStepDraft(
                step_type=StepType.LLM_CALL,
                output=result.message.model_dump(mode="json"),
                input_tokens=result.usage.input_tokens,
                output_tokens=result.usage.output_tokens,
                cost=compute_cost(result.usage, model),
                latency_ms=result.latency_ms,
                **step,
            ),
        )
        return result.message

    def _call_tool(self, run_id: UUID, executor: ToolExecutor, tool_call: ToolCall) -> ChatMessage:
        """Runs one tool call and records it.

        Exists so every tool call, failed or not, reaches the trace and the model.

        Args:
            run_id: The open run.
            executor: The executor of the agent's tools.
            tool_call: The call the model requested.

        Returns:
            ChatMessage: the message that answers the call.
        """
        started_at = time.perf_counter()
        result = executor.execute(tool_call)
        self._recorder.add_step(
            run_id,
            RunStepDraft(
                step_type=result.step_type,
                tool_id=executor.tool_id_of(tool_call.name),
                model_id=result.model_id,
                input={"name": tool_call.name, "arguments": tool_call.arguments},
                output=result.output,
                error=result.error,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost=result.cost,
                latency_ms=elapsed_ms(started_at),
            ),
        )
        return to_tool_message(tool_call, result)
