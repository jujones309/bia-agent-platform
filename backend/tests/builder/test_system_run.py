from decimal import Decimal

import pytest
from pydantic import BaseModel

from bia.builder import system_run
from bia.builder.system_run import SystemAgentRun
from bia.catalog.models.artifacts import ModelSize
from bia.providers.artifacts import MessageRole
from bia.providers.base import ProviderError
from bia.tracing.artifacts import RunOrigin, RunStatus, StepType
from tests.builder.seed import build_execution, build_model
from tests.providers.fake import FakeModelProvider
from tests.tracing.fake import FakeRunRecorder


class _Answer(BaseModel):
    """Stands for a structured contract."""

    value: str


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> FakeModelProvider:
    """Replaces the provider of system runs.

    Args:
        monkeypatch: The patcher of the module.

    Returns:
        FakeModelProvider: the provider they will use.
    """
    fake = FakeModelProvider()
    monkeypatch.setattr(system_run, "get_provider", lambda _name: fake)
    return fake


def test_ask_traces_tokens_and_cost_under_the_exact_version(provider: FakeModelProvider) -> None:
    """Verifies the builder's calls reach the audit record like those of any other agent."""
    recorder = FakeRunRecorder()
    execution = build_execution()
    provider.queue_structured(_Answer(value="ok"))

    with SystemAgentRun(recorder, execution, "necesidad") as run:
        messages = run.initial_messages("datos")
        answer = run.ask(messages, _Answer)
        run.finish("ok")

    assert answer == _Answer(value="ok")
    assert [message.role for message in provider.chat_requests[0]] == [
        MessageRole.SYSTEM,
        MessageRole.USER,
    ]
    assert provider.chat_requests[0][0].content == "Prompt versionado"
    assert provider.requested_models == [execution.model.provider_model_id]
    assert recorder.run.agent_version_id == execution.version.id
    assert recorder.run.origin is RunOrigin.BUILDER
    assert recorder.run.status is RunStatus.SUCCEEDED
    step = recorder.steps[0]
    assert (step.step_type, step.model_id) == (StepType.LLM_CALL, execution.model.id)
    assert step.output == {"value": "ok"}
    assert (step.input_tokens, step.output_tokens) == (10, 5)
    assert step.cost == Decimal(20) / Decimal(1_000_000)


def test_failed_call_is_recorded_and_fails_the_run(provider: FakeModelProvider) -> None:
    """Verifies a failure leaves both the step and the closed run, and still reaches the caller."""
    recorder = FakeRunRecorder()
    provider.queue_structured(ProviderError("timeout"))

    with (
        pytest.raises(ProviderError, match="timeout"),
        SystemAgentRun(recorder, build_execution(), "necesidad") as run,
    ):
        run.ask(run.initial_messages("datos"), _Answer)

    assert recorder.steps[0].error == "timeout"
    assert recorder.steps[0].output is None
    assert recorder.run.status is RunStatus.FAILED
    assert recorder.run.error == "ProviderError: timeout"


def test_any_exception_in_the_block_closes_the_run() -> None:
    """Verifies a failure that is not the provider's cannot leave a run open forever."""
    recorder = FakeRunRecorder()

    with (
        pytest.raises(ValueError, match="respuesta inválida"),
        SystemAgentRun(recorder, build_execution(), "necesidad"),
    ):
        raise ValueError("respuesta inválida")

    assert recorder.run.status is RunStatus.FAILED
    assert recorder.run.error == "ValueError: respuesta inválida"


def test_exception_after_finish_does_not_close_the_run_twice() -> None:
    """Verifies a closed run stays as it was; the fake fails the test on a second close."""
    recorder = FakeRunRecorder()

    with (
        pytest.raises(ValueError, match="después"),
        SystemAgentRun(recorder, build_execution(), "necesidad") as run,
    ):
        run.finish("listo")
        raise ValueError("después")

    assert recorder.run.status is RunStatus.SUCCEEDED
    assert recorder.run.output == "listo"


def test_embed_traces_the_embedding_model_and_not_the_agents_model(
    provider: FakeModelProvider,
) -> None:
    """Verifies the search's cost is attributed to the model that served it."""
    recorder = FakeRunRecorder()
    embedding_model = build_model(ModelSize.EMBEDDING)

    with SystemAgentRun(recorder, build_execution(), "necesidad") as run:
        embedding = run.embed("necesidad", embedding_model)
        run.finish("ok")

    assert len(embedding) == 8
    assert recorder.steps[0].model_id == embedding_model.id
    assert recorder.steps[0].input == ["necesidad"]
    assert recorder.steps[0].output == {"embedding_dimensions": 8}
