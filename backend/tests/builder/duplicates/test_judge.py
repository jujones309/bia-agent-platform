import json
from contextlib import nullcontext
from uuid import uuid4

import pytest

from bia.builder import system_run
from bia.builder.artifacts import DuplicateCandidate, DuplicateVerdict, JudgeDecision
from bia.builder.duplicates import judge
from bia.builder.duplicates.judge import InvalidJudgeDecisionError, judge_need
from bia.builder.system_run import SystemAgentRun
from bia.catalog.models.artifacts import ModelSize
from bia.providers.base import ProviderError
from bia.tracing.artifacts import RunStatus
from tests.builder.seed import build_execution, build_model
from tests.providers.fake import FakeModelProvider
from tests.tracing.fake import FakeRunRecorder

_NEED = "Un bot que responda dudas de facturas"


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> FakeModelProvider:
    """Replaces the provider and the database session of the judge.

    Args:
        monkeypatch: The patcher of the modules.

    Returns:
        FakeModelProvider: the provider the judge will use.
    """
    fake = FakeModelProvider()
    monkeypatch.setattr(system_run, "get_provider", lambda _name: fake)
    monkeypatch.setattr(judge, "database_session", lambda _bind: nullcontext(None))
    return fake


def _candidate(name: str = "Asistente") -> DuplicateCandidate:
    """Builds a candidate.

    Args:
        name: The name of the agent.

    Returns:
        DuplicateCandidate: the candidate.
    """
    return DuplicateCandidate(
        agent_id=uuid4(), name=name, description="Responde dudas", similarity=0.9
    )


def _find_returning(monkeypatch: pytest.MonkeyPatch, candidates: list[DuplicateCandidate]) -> None:
    """Scripts what the search finds.

    Args:
        monkeypatch: The patcher of the module.
        candidates: What it finds.

    Returns:
        None: the search is replaced.
    """
    monkeypatch.setattr(judge, "find_candidates", lambda _session, _embedding: candidates)


def _judge(recorder: FakeRunRecorder) -> tuple:
    """Runs the check inside an open run and closes it.

    Args:
        recorder: Where the trace is written.

    Returns:
        tuple: the result of the check.
    """
    with SystemAgentRun(recorder, build_execution(), _NEED) as run:
        result = judge_need(run, None, _NEED, build_model(ModelSize.EMBEDDING))
        run.finish(result.model_dump_json())
    return result


def test_no_candidates_answers_not_exists_without_calling_the_judge(
    provider: FakeModelProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies nothing is paid for a comparison with nothing; the fake has no scripted answer."""
    _find_returning(monkeypatch, [])
    recorder = FakeRunRecorder()

    result = _judge(recorder)

    assert result.verdict is DuplicateVerdict.NOT_EXISTS
    assert result.candidate is None
    assert provider.chat_requests == []
    assert len(recorder.steps) == 1
    assert recorder.run.status is RunStatus.SUCCEEDED


@pytest.mark.parametrize("verdict", [DuplicateVerdict.EXISTS, DuplicateVerdict.SIMILAR])
def test_verdict_returns_the_chosen_candidate_and_not_the_closest(
    provider: FakeModelProvider, monkeypatch: pytest.MonkeyPatch, verdict: DuplicateVerdict
) -> None:
    """Verifies the judge decides: its choice wins even if the search ranked it second."""
    candidates = [_candidate("Primero"), _candidate("Segundo")]
    _find_returning(monkeypatch, candidates)
    provider.queue_structured(
        JudgeDecision(verdict=verdict, candidate_agent_id=candidates[1].agent_id, reason="Cubre")
    )

    result = _judge(FakeRunRecorder())

    assert result.verdict is verdict
    assert result.candidate == candidates[1]
    assert result.reason == "Cubre"


def test_judge_receives_the_need_and_the_candidates(
    provider: FakeModelProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the model can compare, and that the identifiers it must copy reach it."""
    candidate = _candidate()
    _find_returning(monkeypatch, [candidate])
    provider.queue_structured(
        JudgeDecision(
            verdict=DuplicateVerdict.NOT_EXISTS, candidate_agent_id=None, reason="Es otro tema"
        )
    )

    result = _judge(FakeRunRecorder())

    payload = json.loads(provider.chat_requests[0][1].content)
    assert payload["necesidad"] == _NEED
    assert payload["candidatos"][0]["agent_id"] == str(candidate.agent_id)
    assert result.verdict is DuplicateVerdict.NOT_EXISTS
    assert result.candidate is None


def test_invented_candidate_is_a_hard_error_and_fails_the_run(
    provider: FakeModelProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the person is never asked to confirm an agent the search did not find."""
    _find_returning(monkeypatch, [_candidate()])
    provider.queue_structured(
        JudgeDecision(verdict=DuplicateVerdict.EXISTS, candidate_agent_id=uuid4(), reason="Cubre")
    )
    recorder = FakeRunRecorder()

    with pytest.raises(InvalidJudgeDecisionError, match="not one of the candidates"):
        _judge(recorder)

    assert recorder.run.status is RunStatus.FAILED


def test_exists_without_candidate_is_a_hard_error(
    provider: FakeModelProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies a verdict that points at nothing does not pass as a usable answer."""
    _find_returning(monkeypatch, [_candidate()])
    provider.queue_structured(
        JudgeDecision(verdict=DuplicateVerdict.EXISTS, candidate_agent_id=None, reason="Cubre")
    )

    with pytest.raises(InvalidJudgeDecisionError):
        _judge(FakeRunRecorder())


def test_not_exists_with_a_candidate_is_a_hard_error(
    provider: FakeModelProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies a contradictory answer is not silently read as either of its halves."""
    candidate = _candidate()
    _find_returning(monkeypatch, [candidate])
    provider.queue_structured(
        JudgeDecision(
            verdict=DuplicateVerdict.NOT_EXISTS,
            candidate_agent_id=candidate.agent_id,
            reason="Cubre",
        )
    )

    with pytest.raises(InvalidJudgeDecisionError, match="said not_exists"):
        _judge(FakeRunRecorder())


def test_provider_failure_reaches_the_caller_with_the_run_closed(
    provider: FakeModelProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies a failed judge is not read as "no duplicate", which would create a duplicate."""
    _find_returning(monkeypatch, [_candidate()])
    provider.queue_structured(ProviderError("timeout"))
    recorder = FakeRunRecorder()

    with pytest.raises(ProviderError, match="timeout"):
        _judge(recorder)

    assert recorder.run.status is RunStatus.FAILED
