from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import sentinel
from uuid import UUID, uuid4

import pytest

from bia.agents.artifacts import AgentSpec, AgentVersion
from bia.catalog.models.artifacts import CatalogModel, ModelSize
from bia.catalog.tools.artifacts import CatalogTool, ToolResult
from bia.catalog.tools.consultar_factura import ConsultarFacturaTool
from bia.providers.artifacts import MessageRole, ProviderName, ToolCall
from bia.providers.base import ProviderError
from bia.runtime import tools as runtime_tools
from bia.runtime.execution import AgentExecution
from bia.runtime.messages import build_initial_messages
from bia.runtime.runner import AgentRunner
from bia.tracing.artifacts import RunOrigin, RunStatus, StepType
from tests.providers.fake import FakeModelProvider
from tests.tracing.fake import FakeRunRecorder

_VALID_ARGUMENTS = '{"numero_cliente": "100001"}'


def _execution(max_iterations: int = 5) -> AgentExecution:
    """Builds an agent with the real invoice tool and a model priced at 1 and 2 USD per 1M.

    Args:
        max_iterations: The iteration limit of the spec.

    Returns:
        AgentExecution: the execution.
    """
    now = datetime.now(UTC)
    tool = ConsultarFacturaTool()
    model = CatalogModel(
        id=uuid4(),
        name="Model",
        provider=ProviderName.OPENAI,
        provider_model_id="catalog-model",
        size=ModelSize.SMALL,
        input_cost_per_million=Decimal(1),
        output_cost_per_million=Decimal(2),
        context_window=1000,
        recommended_use="Tests",
        is_active=True,
        created_at=now,
    )
    spec = AgentSpec(
        purpose="Facturas",
        system_prompt="Eres útil",
        model_id=model.id,
        tool_names=[tool.name],
        max_iterations=max_iterations,
    )
    version = AgentVersion(
        id=uuid4(),
        agent_id=uuid4(),
        version_number=1,
        spec=spec,
        designer_justification=None,
        created_at=now,
    )
    catalog_tool = CatalogTool(
        id=uuid4(),
        name=tool.name,
        description=tool.description,
        parameters_schema=tool.parameters_schema,
        risk_level=tool.risk_level,
        is_active=True,
        created_at=now,
    )
    return AgentExecution(version, model, [catalog_tool])


def _tool_call(arguments: str = _VALID_ARGUMENTS) -> ToolCall:
    """Builds a call to the invoice tool.

    Args:
        arguments: The raw JSON arguments.

    Returns:
        ToolCall: the call.
    """
    return ToolCall(id="call-1", name="consultar_factura", arguments=arguments)


@pytest.fixture
def provider() -> FakeModelProvider:
    """Provides a provider with nothing scripted.

    Returns:
        FakeModelProvider: the provider.
    """
    return FakeModelProvider()


@pytest.fixture
def recorder() -> FakeRunRecorder:
    """Provides a recorder without a database.

    Returns:
        FakeRunRecorder: the recorder.
    """
    return FakeRunRecorder()


def test_direct_answer_closes_the_run_as_succeeded(
    provider: FakeModelProvider, recorder: FakeRunRecorder
) -> None:
    """Verifies the catalog model is called, its cost traced and the answer returned."""
    provider.queue_text("Hola")
    execution = _execution()

    result = AgentRunner(recorder, provider, sentinel.bind).run(
        execution, "hola", RunOrigin.PLAYGROUND
    )

    assert (result.status, result.output, result.error) == (RunStatus.SUCCEEDED, "Hola", None)
    assert result.run_id == recorder.run.id
    assert recorder.run.origin is RunOrigin.PLAYGROUND
    assert recorder.run.agent_version_id == execution.version.id
    assert provider.requested_models == ["catalog-model"]
    assert provider.offered_tools[0][0].name == "consultar_factura"
    step = recorder.steps[0]
    assert (step.step_type, step.model_id) == (StepType.LLM_CALL, execution.model.id)
    assert (step.input_tokens, step.output_tokens) == (10, 5)
    assert step.cost == Decimal("0.00002")  # 10 * 1 + 5 * 2, per million
    assert step.input[0]["content"] == "Eres útil"


def test_tool_result_goes_back_to_the_model_and_to_the_trace(
    provider: FakeModelProvider, recorder: FakeRunRecorder
) -> None:
    """Verifies the second model call sees the real tool output, and every step is traced."""
    provider.queue_tool_calls([_tool_call()])
    provider.queue_text("Tu saldo es tal")
    execution = _execution()

    result = AgentRunner(recorder, provider, sentinel.bind).run(
        execution, "saldo", RunOrigin.PLAYGROUND
    )

    assert result.output == "Tu saldo es tal"
    assert [step.step_type for step in recorder.steps] == [
        StepType.LLM_CALL,
        StepType.TOOL_CALL,
        StepType.LLM_CALL,
    ]
    tool_step = recorder.steps[1]
    expected = ConsultarFacturaTool().run({"numero_cliente": "100001"}, sentinel.context).output
    assert tool_step.output == expected
    assert tool_step.tool_id == execution.tools[0].id
    roles = [message.role for message in provider.chat_requests[1]]
    assert roles[-2:] == [MessageRole.ASSISTANT, MessageRole.TOOL]
    assert str(expected["saldo_cop"]) in provider.chat_requests[1][-1].content


def test_tool_error_reaches_the_model_without_breaking_the_loop(
    provider: FakeModelProvider, recorder: FakeRunRecorder
) -> None:
    """Verifies the model can recover from a bad call, and the failed step is on record."""
    provider.queue_tool_calls([_tool_call("{}")])
    provider.queue_text("¿Cuál es tu número de cliente?")

    result = AgentRunner(recorder, provider, sentinel.bind).run(
        _execution(), "saldo", RunOrigin.PLAYGROUND
    )

    assert result.status is RunStatus.SUCCEEDED
    assert "numero_cliente" in recorder.steps[1].error
    assert recorder.steps[1].output is None
    assert "error" in provider.chat_requests[1][-1].content


def test_every_tool_call_of_a_reply_is_answered(
    provider: FakeModelProvider, recorder: FakeRunRecorder
) -> None:
    """Verifies parallel requests each get a result, as providers reject unanswered calls."""
    second = ToolCall(id="call-2", name="consultar_factura", arguments=_VALID_ARGUMENTS)
    provider.queue_tool_calls([_tool_call(), second])
    provider.queue_text("Listo")

    AgentRunner(recorder, provider, sentinel.bind).run(_execution(), "saldo", RunOrigin.PLAYGROUND)

    answered = [message.tool_call_id for message in provider.chat_requests[1][-2:]]
    assert answered == ["call-1", "call-2"]


def test_iteration_limit_fails_the_run_after_exactly_that_many_calls(
    provider: FakeModelProvider, recorder: FakeRunRecorder
) -> None:
    """Verifies a model stuck on tools cannot spend without bound, and the reason is kept."""
    for _ in range(2):
        provider.queue_tool_calls([_tool_call()])

    result = AgentRunner(recorder, provider, sentinel.bind).run(
        _execution(2), "saldo", RunOrigin.PLAYGROUND
    )

    assert result.status is RunStatus.FAILED
    assert result.output is None
    assert "limit of 2 iterations" in result.error
    assert len(provider.chat_requests) == 2


def test_provider_failure_is_traced_and_reported_without_raising(
    provider: FakeModelProvider, recorder: FakeRunRecorder
) -> None:
    """Verifies a failed model call leaves its step, a closed run and the reason."""
    provider.queue_chat_error(ProviderError("Se agotó el tiempo"))
    execution = _execution()

    result = AgentRunner(recorder, provider, sentinel.bind).run(
        execution, "hola", RunOrigin.PLAYGROUND
    )

    assert (result.status, result.error) == (RunStatus.FAILED, "Se agotó el tiempo")
    assert recorder.run.status is RunStatus.FAILED
    step = recorder.steps[0]
    assert (step.error, step.model_id) == ("Se agotó el tiempo", execution.model.id)


def test_unexpected_crash_closes_the_run_and_propagates(recorder: FakeRunRecorder) -> None:
    """Verifies a bug is not hidden, and still cannot leave a run stuck in running."""
    provider = FakeModelProvider()  # nothing scripted: the call raises AssertionError

    with pytest.raises(AssertionError):
        AgentRunner(recorder, provider, sentinel.bind).run(
            _execution(), "hola", RunOrigin.PLAYGROUND
        )

    assert recorder.run.status is RunStatus.FAILED
    assert "AssertionError" in recorder.run.error


class _RetrievalTool:
    """Stands for a tool that calls a model and captures what the execution gives it."""

    def __init__(self, result: ToolResult) -> None:
        """Keeps the result to return.

        Args:
            result (ToolResult): What `run` returns.
        """
        self._result = result
        self.contexts: list[object] = []

    def run(self, _args: dict[str, object], context: object) -> ToolResult:
        """Records the context and returns the kept result.

        Args:
            _args: The unused arguments.
            context: What the runner provides.

        Returns:
            ToolResult: the kept result.
        """
        self.contexts.append(context)
        return self._result


def test_a_tool_decides_its_step_type_and_its_model_spend_reaches_the_trace(
    provider: FakeModelProvider, recorder: FakeRunRecorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies an embedding inside a tool is traced, and the tool receives the spec's base."""
    embedding_model_id = uuid4()
    tool = _RetrievalTool(
        ToolResult(
            output={"chunks": []},
            step_type=StepType.RETRIEVAL,
            model_id=embedding_model_id,
            input_tokens=7,
            cost=Decimal("0.5"),
        )
    )
    monkeypatch.setattr(runtime_tools, "get_tool", lambda _name: tool)
    provider.queue_tool_calls([_tool_call()])
    provider.queue_text("Listo")
    execution = _execution()
    base_id = uuid4()
    spec = execution.version.spec.model_copy(update={"knowledge_base_id": base_id})
    version = execution.version.model_copy(update={"spec": spec})

    AgentRunner(recorder, provider, sentinel.bind).run(
        AgentExecution(version, execution.model, execution.tools), "hola", RunOrigin.PLAYGROUND
    )

    step = recorder.steps[1]
    assert step.step_type is StepType.RETRIEVAL
    assert (step.model_id, step.input_tokens, step.cost) == (embedding_model_id, 7, Decimal("0.5"))
    assert step.tool_id == execution.tools[0].id
    assert tool.contexts[0].knowledge_base_id == base_id
    assert tool.contexts[0].bind is sentinel.bind


def _open_run(recorder: FakeRunRecorder, execution: AgentExecution) -> UUID:
    """Opens a conversation in the fake recorder.

    Args:
        recorder: The fake recorder.
        execution: The execution of the conversation.

    Returns:
        UUID: the identifier of the open run.
    """
    version = execution.version
    return recorder.start_run(version.agent_id, version.id, RunOrigin.PLAYGROUND, "hola").id


def test_turn_with_an_answer_leaves_the_run_open(
    provider: FakeModelProvider, recorder: FakeRunRecorder
) -> None:
    """Verifies an answer does not end a conversation, and that it is kept in the run."""
    execution = _execution()
    run_id = _open_run(recorder, execution)
    provider.queue_text("Hola")
    messages = build_initial_messages(execution.version.spec, "hola")

    result = AgentRunner(recorder, provider, sentinel.bind).run_turn(run_id, execution, messages)

    assert (result.status, result.output) == (RunStatus.RUNNING, "Hola")
    assert (recorder.run.status, recorder.run.output) == (RunStatus.RUNNING, "Hola")


def test_turn_with_a_provider_failure_keeps_the_conversation_and_its_last_answer(
    provider: FakeModelProvider, recorder: FakeRunRecorder
) -> None:
    """Verifies a failed turn reports why, without losing what the conversation had."""
    execution = _execution()
    run_id = _open_run(recorder, execution)
    runner = AgentRunner(recorder, provider, sentinel.bind)
    spec = execution.version.spec
    provider.queue_text("Hola")
    runner.run_turn(run_id, execution, build_initial_messages(spec, "uno"))
    provider.queue_chat_error(ProviderError("timeout"))

    result = runner.run_turn(run_id, execution, build_initial_messages(spec, "dos"))

    assert (result.status, result.output) == (RunStatus.RUNNING, None)
    assert "timeout" in result.error
    assert (recorder.run.status, recorder.run.output) == (RunStatus.RUNNING, "Hola")


def test_turn_reaching_the_iteration_limit_leaves_the_run_open(
    provider: FakeModelProvider, recorder: FakeRunRecorder
) -> None:
    """Verifies the limit applies to each turn and is not the end of the conversation."""
    execution = _execution(1)
    run_id = _open_run(recorder, execution)
    provider.queue_tool_calls([_tool_call()])
    messages = build_initial_messages(execution.version.spec, "saldo")

    result = AgentRunner(recorder, provider, sentinel.bind).run_turn(run_id, execution, messages)

    assert result.status is RunStatus.RUNNING
    assert "limit of 1 iterations" in result.error


def test_turn_with_an_unexpected_error_closes_the_run_and_propagates(
    provider: FakeModelProvider, recorder: FakeRunRecorder
) -> None:
    """Verifies a bug surfaces and leaves no conversation open behind it."""
    execution = _execution()
    run_id = _open_run(recorder, execution)
    messages = build_initial_messages(execution.version.spec, "hola")

    with pytest.raises(AssertionError):  # the fake provider has nothing scripted
        AgentRunner(recorder, provider, sentinel.bind).run_turn(run_id, execution, messages)

    assert recorder.run.status is RunStatus.FAILED
