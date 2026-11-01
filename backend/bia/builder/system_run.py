import logging
import time
from types import TracebackType
from typing import Self
from uuid import UUID

from pydantic import BaseModel, JsonValue

from bia.catalog.models.artifacts import CatalogModel
from bia.providers.artifacts import ChatMessage, TokenUsage
from bia.providers.base import ProviderError
from bia.providers.cost import compute_cost
from bia.providers.factory import get_provider
from bia.runtime.execution import AgentExecution
from bia.runtime.messages import build_initial_messages
from bia.runtime.runner import elapsed_ms
from bia.tracing.artifacts import RunOrigin, RunStepDraft, StepType
from bia.tracing.recorder import RunRecorder

logger = logging.getLogger(__name__)


class SystemAgentRun:
    """Traces the work of a system agent as one run, as a context manager.

    Exists because the judge and the designer need structured answers, which the tool-calling loop
    of `AgentRunner` does not produce, yet every LLM call must be traced. Guarantees that each call
    is recorded, even if it fails, and that the run ends closed: leaving the block on an exception
    fails the run and lets the exception propagate. Consumed by `bia/builder/`.
    """

    def __init__(self, recorder: RunRecorder, execution: AgentExecution, input_text: str) -> None:
        """Prepares a run that starts when the block is entered.

        Args:
            recorder (RunRecorder): Where the trace is written.
            execution (AgentExecution): The active version of the system agent, with its model.
            input_text (str): The need the agent received.
        """
        self._recorder = recorder
        self._execution = execution
        self._input_text = input_text
        self._run_id: UUID | None = None
        self._is_open = False

    def __enter__(self) -> Self:
        """Opens the run.

        Exists so the run is visible from before its first call.

        Returns:
            Self: the open run.
        """
        version = self._execution.version
        run = self._recorder.start_run(
            version.agent_id, version.id, RunOrigin.BUILDER, self._input_text
        )
        self._run_id = run.id
        self._is_open = True
        return self

    def __exit__(
        self,
        error_type: type[BaseException] | None,
        error: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        """Fails the run if the block ended on an exception; never swallows it.

        Exists so no failure leaves a run open forever. An exception after `finish` leaves the
        run as it was, because a closed run cannot change.

        Args:
            error_type: The class of the exception, if any.
            error: The exception, if any.
            _traceback: Its traceback; required by the protocol.

        Returns:
            None: a falsy return is what lets the exception propagate.
        """
        if error is None or not self._is_open:
            return
        logger.warning("Run %s of a system agent failed: %s", self._run_id, error)
        self._is_open = False
        self._recorder.fail_run(self._run_id, f"{error_type.__name__}: {error}")

    def initial_messages(self, input_text: str) -> list[ChatMessage]:
        """Builds the conversation of a call from the active spec.

        Exists so the prompt that reaches the model is the versioned one, assembled like that of
        any other agent.

        Args:
            input_text: The content of the user message, with the data of the task.

        Returns:
            list[ChatMessage]: the system message followed by the user message.
        """
        return build_initial_messages(self._execution.version.spec, input_text)

    def ask[ResponseT: BaseModel](
        self, messages: list[ChatMessage], response_model: type[ResponseT]
    ) -> ResponseT:
        """Calls the agent's model for a structured answer, and records the call.

        Exists as the only way the judge and the designer reach their model.

        Args:
            messages: The conversation so far.
            response_model: The contract the answer must validate against.

        Returns:
            ResponseT: the validated answer.

        Raises:
            ProviderError: If the call fails, after recording it.
        """
        model = self._execution.model
        trace_input = [message.model_dump(mode="json") for message in messages]
        started_at = time.perf_counter()
        try:
            result = get_provider(model.provider).chat_structured(
                messages, response_model, model.provider_model_id
            )
        except ProviderError as error:
            self._record_failure(model, trace_input, error, started_at)
            raise
        output = result.parsed.model_dump(mode="json")
        self._record_success(model, trace_input, output, result.usage, result.latency_ms)
        return result.parsed

    def embed(self, input_text: str, model: CatalogModel) -> list[float]:
        """Generates the embedding of a text, and records the call.

        Exists so the search of the duplicate check is part of its trace and of its cost.

        Args:
            input_text: The text to embed.
            model: The catalog's embedding model.

        Returns:
            list[float]: the vector.

        Raises:
            ProviderError: If the call fails, after recording it.
        """
        started_at = time.perf_counter()
        try:
            result = get_provider(model.provider).embed([input_text], model.provider_model_id)
        except ProviderError as error:
            self._record_failure(model, [input_text], error, started_at)
            raise
        embedding = result.embeddings[0]
        output = {"embedding_dimensions": len(embedding)}
        self._record_success(model, [input_text], output, result.usage, result.latency_ms)
        return embedding

    def finish(self, output: str) -> None:
        """Closes the run as succeeded.

        Exists so the totals are summed once all the calls were recorded.

        Args:
            output: What the agent produced, as text.

        Returns:
            None: the run is closed.
        """
        self._is_open = False
        self._recorder.finish_run(self._run_id, output)

    def _record_success(
        self,
        model: CatalogModel,
        trace_input: JsonValue,
        output: JsonValue,
        usage: TokenUsage,
        latency_ms: int,
    ) -> None:
        """Records a model call that worked, with what it cost.

        Exists as the shared write of `ask` and `embed`.

        Args:
            model: The model that served the call.
            trace_input: What the model received.
            output: What the model returned.
            usage: The tokens the call consumed.
            latency_ms: How long the call took.

        Returns:
            None: the step is written.
        """
        self._recorder.add_step(
            self._run_id,
            RunStepDraft(
                step_type=StepType.LLM_CALL,
                model_id=model.id,
                input=trace_input,
                output=output,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cost=compute_cost(usage, model),
                latency_ms=latency_ms,
            ),
        )

    def _record_failure(
        self,
        model: CatalogModel,
        trace_input: JsonValue,
        error: ProviderError,
        started_at: float,
    ) -> None:
        """Records a model call that failed.

        Exists as the shared write of `ask` and `embed`, so no call escapes the trace.

        Args:
            model: The model that was called.
            trace_input: What the model received.
            error: Why the call failed.
            started_at: The `time.perf_counter` reading from before the call.

        Returns:
            None: the step is written.
        """
        self._recorder.add_step(
            self._run_id,
            RunStepDraft(
                step_type=StepType.LLM_CALL,
                model_id=model.id,
                input=trace_input,
                error=str(error),
                latency_ms=elapsed_ms(started_at),
            ),
        )
