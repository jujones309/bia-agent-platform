from uuid import uuid4

import pytest

from bia.builder import system_run
from bia.evals.artifacts import EvalCase, EvalCaseOrigin, EvalJudgement, EvalVerdict
from bia.evals.runner import _EvalPlan, _evaluate_case
from bia.providers.base import ProviderError
from bia.runtime.runner import AgentRunner
from bia.tracing.artifacts import RunOrigin
from tests.builder.seed import build_execution
from tests.providers.fake import FakeModelProvider
from tests.tracing.fake import FakeRunRecorder


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> FakeModelProvider:
    """Replaces the provider of the judge.

    Args:
        monkeypatch: The patcher of the module.

    Returns:
        FakeModelProvider: the provider of both the agent and the judge.
    """
    fake = FakeModelProvider()
    monkeypatch.setattr(system_run, "get_provider", lambda _name: fake)
    return fake


def _evaluate(provider: FakeModelProvider, recorder: FakeRunRecorder) -> tuple[str, EvalJudgement]:
    """Evaluates a fixed case.

    Args:
        provider: The provider of the agent.
        recorder: Where the runs are written.

    Returns:
        tuple[str, EvalJudgement]: the answer and the decision.
    """
    case = EvalCase(
        id=uuid4(),
        agent_id=uuid4(),
        input="¿Saldo?",
        expected_behavior="Informa el saldo",
        origin=EvalCaseOrigin.MANUAL,
        created_at="2026-10-31T00:00:00Z",
    )
    plan = _EvalPlan(build_execution(), build_execution(), [case])
    return _evaluate_case(AgentRunner(recorder, provider, None), recorder, plan, case)


def test_the_answer_of_the_runtime_is_what_the_judge_decides_on(
    provider: FakeModelProvider,
) -> None:
    """Verifies the case goes through the real loop, and the judge sees its final answer."""
    provider.queue_text("Son 100")
    decision = EvalJudgement(verdict=EvalVerdict.PASS, score=90, reason="Cumple")
    provider.queue_structured(decision)

    output, judgement = _evaluate(provider, FakeRunRecorder())

    assert output == "Son 100"
    assert judgement == decision
    assert provider.chat_requests[0][-1].content == "¿Saldo?"
    assert "Son 100" in provider.chat_requests[1][-1].content


def test_an_agent_without_an_answer_fails_the_case_without_paying_the_judge(
    provider: FakeModelProvider,
) -> None:
    """Verifies the reason reaches the person; the fake has no scripted judge answer to consume."""
    provider.queue_chat_error(ProviderError("timeout"))
    recorder = FakeRunRecorder()

    output, judgement = _evaluate(provider, recorder)

    assert output == ""
    assert judgement.verdict is EvalVerdict.FAIL
    assert judgement.score == 0
    assert "timeout" in judgement.reason
    assert recorder.run.origin is RunOrigin.EVAL
