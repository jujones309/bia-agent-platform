import json

import pytest

from bia.builder import system_run
from bia.evals.artifacts import EvalJudgement, EvalVerdict
from bia.evals.judge import InvalidEvalJudgementError, judge_answer
from bia.providers.base import ProviderError
from bia.tracing.artifacts import RunOrigin, RunStatus
from tests.builder.seed import build_execution
from tests.providers.fake import FakeModelProvider
from tests.tracing.fake import FakeRunRecorder


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> FakeModelProvider:
    """Replaces the provider of the judge.

    Args:
        monkeypatch: The patcher of the module.

    Returns:
        FakeModelProvider: the provider the judge will use.
    """
    fake = FakeModelProvider()
    monkeypatch.setattr(system_run, "get_provider", lambda _name: fake)
    return fake


def _judge(recorder: FakeRunRecorder) -> EvalJudgement:
    """Judges a fixed answer.

    Args:
        recorder: Where the trace is written.

    Returns:
        EvalJudgement: the decision.
    """
    return judge_answer(recorder, build_execution(), "¿Saldo?", "Informa el saldo", "Son 100")


def test_judge_receives_the_comparison_and_traces_it_as_an_eval(
    provider: FakeModelProvider,
) -> None:
    """Verifies the model can compare, and its cost is not attributed to the builder."""
    decision = EvalJudgement(verdict=EvalVerdict.PASS, score=90, reason="Cumple")
    provider.queue_structured(decision)
    recorder = FakeRunRecorder()

    assert _judge(recorder) == decision

    payload = json.loads(provider.chat_requests[0][1].content)
    assert payload == {
        "entrada": "¿Saldo?",
        "comportamiento_esperado": "Informa el saldo",
        "respuesta": "Son 100",
        "puntaje_minimo_para_aprobar": 70,
    }
    assert recorder.run.origin is RunOrigin.EVAL
    assert recorder.run.status is RunStatus.SUCCEEDED
    assert recorder.run.input == "¿Saldo?"


@pytest.mark.parametrize(
    ("verdict", "score"),
    [
        (EvalVerdict.PASS, 70),
        (EvalVerdict.FAIL, 69.99),
        (EvalVerdict.PASS, 100),
        (EvalVerdict.FAIL, 0),
    ],
)
def test_scores_that_fit_the_verdict_are_accepted_at_the_limits(
    provider: FakeModelProvider, verdict: EvalVerdict, score: float
) -> None:
    """Verifies the cutoff sits exactly at the passing score."""
    provider.queue_structured(EvalJudgement(verdict=verdict, score=score, reason="Motivo"))

    assert _judge(FakeRunRecorder()).verdict is verdict


@pytest.mark.parametrize(
    ("verdict", "score", "reason"),
    [
        (EvalVerdict.PASS, 20, "Motivo"),
        (EvalVerdict.FAIL, 95, "Motivo"),
        (EvalVerdict.PASS, 101, "Motivo"),
        (EvalVerdict.FAIL, -1, "Motivo"),
        (EvalVerdict.PASS, 90, "   "),
    ],
)
def test_unusable_answers_are_hard_errors_and_fail_the_run(
    provider: FakeModelProvider, verdict: EvalVerdict, score: float, reason: str
) -> None:
    """Verifies the gate never decides on a contradiction, or on a pass nobody can explain."""
    provider.queue_structured(EvalJudgement(verdict=verdict, score=score, reason=reason))
    recorder = FakeRunRecorder()

    with pytest.raises(InvalidEvalJudgementError):
        _judge(recorder)

    assert recorder.run.status is RunStatus.FAILED


def test_provider_failure_reaches_the_caller_with_the_run_closed(
    provider: FakeModelProvider,
) -> None:
    """Verifies a failed judge is not read as a verdict on the agent."""
    provider.queue_structured(ProviderError("timeout"))
    recorder = FakeRunRecorder()

    with pytest.raises(ProviderError, match="timeout"):
        _judge(recorder)

    assert recorder.run.status is RunStatus.FAILED
