import json
from contextlib import nullcontext
from uuid import uuid4

import pytest

from bia.agents.validation import InvalidAgentSpecError
from bia.builder import system_run
from bia.builder.artifacts import AgentDesign, DesignerJustification
from bia.builder.designer import designer
from bia.builder.designer.designer import DesignCatalog, InvalidProposalError, design_agent
from bia.builder.system_run import SystemAgentRun
from bia.providers.artifacts import MessageRole
from bia.providers.base import ProviderError
from bia.tracing.artifacts import RunStatus
from tests.builder.seed import build_execution, build_model
from tests.providers.fake import FakeModelProvider
from tests.tracing.fake import FakeRunRecorder

_NEED = "Responder dudas de facturas"
_UNKNOWN_MODEL_PROBLEM = "The model catalog has no entry with id 123"


class _ScriptedValidation:
    """Stands for `validate_new_spec`, failing with the scripted problems in order."""

    def __init__(self, problems: list[str | None]) -> None:
        """Keeps the outcomes.

        Args:
            problems (list[str | None]): The problem of each call; None means valid.
        """
        self._problems = problems

    def __call__(self, _session: object, _spec: object) -> None:
        """Raises the next problem, if there is one.

        Args:
            _session: The unused session.
            _spec: The unused spec.

        Returns:
            None: the spec is valid.

        Raises:
            InvalidAgentSpecError: If that is what was scripted.
        """
        problem = self._problems.pop(0)
        if problem is not None:
            raise InvalidAgentSpecError(problem)


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> FakeModelProvider:
    """Replaces the provider and the database session of the designer.

    Args:
        monkeypatch: The patcher of the modules.

    Returns:
        FakeModelProvider: the provider the designer will use.
    """
    fake = FakeModelProvider()
    monkeypatch.setattr(system_run, "get_provider", lambda _name: fake)
    monkeypatch.setattr(designer, "database_session", lambda _bind: nullcontext(None))
    return fake


def _design(**changes: object) -> AgentDesign:
    """Builds an answer of the designer.

    Args:
        changes: The values that differ from a valid design.

    Returns:
        AgentDesign: the answer.
    """
    justification = DesignerJustification(
        model="Es barato", tools="Consulta saldos", knowledge_base="No aplica", guardrails="Evita"
    )
    values = {
        "name": "Asistente",
        "purpose": "Facturas",
        "system_prompt": "Eres útil",
        "model_id": uuid4(),
        "tool_names": ["consultar_factura"],
        "knowledge_base_id": None,
        "guardrails": ["No inventes saldos"],
        "max_iterations": 5,
        "justification": justification,
    }
    return AgentDesign(**{**values, **changes})


def _run_design(recorder: FakeRunRecorder) -> object:
    """Runs the designer inside an open run and closes it.

    Args:
        recorder: Where the trace is written.

    Returns:
        object: the proposal.
    """
    catalog = DesignCatalog(models=[build_model()], tools=[], knowledge_bases=[])
    with SystemAgentRun(recorder, build_execution(), _NEED) as run:
        proposal = design_agent(run, None, _NEED, catalog)
        run.finish(proposal.model_dump_json())
    return proposal


def test_valid_design_becomes_a_proposal_without_retrying(
    provider: FakeModelProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the decisions of the model are what is proposed; the fake has one answer."""
    monkeypatch.setattr(designer, "validate_new_spec", _ScriptedValidation([None]))
    design = _design()
    provider.queue_structured(design)

    proposal = _run_design(FakeRunRecorder())

    assert proposal.name == "Asistente"
    assert proposal.spec.model_id == design.model_id
    assert proposal.spec.tool_names == ["consultar_factura"]
    assert proposal.spec.guardrails == ["No inventes saldos"]
    assert proposal.justification == design.justification


def test_designer_receives_the_need_and_what_it_may_choose_from(
    provider: FakeModelProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the model sees the ids to copy and the costs to weigh, but no provider ids."""
    monkeypatch.setattr(designer, "validate_new_spec", _ScriptedValidation([None]))
    provider.queue_structured(_design())

    _run_design(FakeRunRecorder())

    payload = json.loads(provider.chat_requests[0][1].content)
    assert payload["necesidad"] == _NEED
    assert set(payload) == {"necesidad", "modelos", "herramientas", "bases_de_conocimiento"}
    offered = payload["modelos"][0]
    assert offered["input_cost_per_million"] == "1"
    assert "id" in offered
    assert "recommended_use" in offered
    assert "provider_model_id" not in offered


def test_invalid_design_is_retried_once_with_the_reason(
    provider: FakeModelProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the retry shows the model its answer and what to fix, and both calls are traced."""
    monkeypatch.setattr(
        designer, "validate_new_spec", _ScriptedValidation([_UNKNOWN_MODEL_PROBLEM, None])
    )
    corrected = _design(name="Corregido")
    provider.queue_structured(_design(name="Inventado"))
    provider.queue_structured(corrected)
    recorder = FakeRunRecorder()

    proposal = _run_design(recorder)

    assert proposal.name == "Corregido"
    retry_messages = provider.chat_requests[1]
    assert [message.role for message in retry_messages[-2:]] == [
        MessageRole.ASSISTANT,
        MessageRole.USER,
    ]
    assert "Inventado" in retry_messages[-2].content
    assert json.loads(retry_messages[-1].content) == {
        "problemas_de_validacion": _UNKNOWN_MODEL_PROBLEM
    }
    assert len(recorder.steps) == 2
    assert recorder.run.status is RunStatus.SUCCEEDED


def test_second_invalid_design_is_a_hard_error_with_the_run_failed(
    provider: FakeModelProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies it retries only once, and that an invented reference never becomes an agent."""
    monkeypatch.setattr(
        designer,
        "validate_new_spec",
        _ScriptedValidation([_UNKNOWN_MODEL_PROBLEM, _UNKNOWN_MODEL_PROBLEM]),
    )
    provider.queue_structured(_design())
    provider.queue_structured(_design())
    recorder = FakeRunRecorder()

    with pytest.raises(InvalidProposalError, match=_UNKNOWN_MODEL_PROBLEM):
        _run_design(recorder)

    assert len(provider.chat_requests) == 2
    assert recorder.run.status is RunStatus.FAILED


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"max_iterations": 99}, "max_iterations"),
        ({"purpose": ""}, "purpose"),
        ({"name": "  "}, "name"),
    ],
)
def test_design_that_breaks_the_spec_rules_is_retried_too(
    provider: FakeModelProvider,
    monkeypatch: pytest.MonkeyPatch,
    changes: dict[str, object],
    field: str,
) -> None:
    """Verifies limits the wire format cannot express reach the same retry as invented ids."""
    monkeypatch.setattr(designer, "validate_new_spec", _ScriptedValidation([None]))
    provider.queue_structured(_design(**changes))
    provider.queue_structured(_design())

    proposal = _run_design(FakeRunRecorder())

    assert field in provider.chat_requests[1][-1].content
    assert proposal.spec.max_iterations == 5


def test_provider_failure_is_not_retried(
    provider: FakeModelProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the retry is for invalid designs; the SDK already retries transport failures."""
    provider.queue_structured(ProviderError("timeout"))
    recorder = FakeRunRecorder()

    with pytest.raises(ProviderError, match="timeout"):
        _run_design(recorder)

    assert recorder.run.status is RunStatus.FAILED
