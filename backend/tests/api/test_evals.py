from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from bia.agents.artifacts import (
    Agent,
    AgentDetail,
    AgentKind,
    AgentSpec,
    AgentStatus,
    AgentVersion,
)
from bia.agents.repository import ActiveVersionNotFoundError, AgentNotFoundError
from bia.api import evals as evals_router
from bia.api.dependencies import get_database_engine, get_session
from bia.api.main import app
from bia.evals.artifacts import (
    DriftReport,
    EvalCase,
    EvalCaseOrigin,
    EvalReport,
    PublishRejection,
)
from bia.evals.cases import CasesAlreadyGeneratedError, NoUsableCasesError
from bia.evals.gate import AgentNotEvaluableError, PublishRejectedError
from bia.evals.judge import InvalidEvalJudgementError
from bia.evals.runner import NoEvalCasesError
from bia.providers.base import ProviderError
from bia.runtime.execution import AgentConfigurationError
from bia.tracing.artifacts import RunOrigin

_AGENT_ID = uuid4()


@pytest.fixture
def client(api_client: TestClient) -> TestClient:
    """Provides an authenticated client that never reaches a real database.

    Args:
        api_client: The authenticated client.

    Returns:
        TestClient: the client.
    """
    app.dependency_overrides[get_database_engine] = lambda: None
    app.dependency_overrides[get_session] = lambda: None
    return api_client


class _Raiser:
    """Stands for an evals function that fails; a class because nested functions are banned."""

    def __init__(self, error: Exception) -> None:
        """Keeps the error.

        Args:
            error (Exception): The error to raise when called.
        """
        self._error = error

    def __call__(self, *_args: object) -> None:
        """Raises the kept error.

        Args:
            _args: The unused arguments of the replaced function.

        Returns:
            None: never.

        Raises:
            Exception: The kept error.
        """
        raise self._error


def _case() -> EvalCase:
    """Builds a stored case.

    Returns:
        EvalCase: the case.
    """
    return EvalCase(
        id=uuid4(),
        agent_id=_AGENT_ID,
        input="¿Saldo?",
        expected_behavior="Informa el saldo",
        origin=EvalCaseOrigin.MANUAL,
        created_at=datetime.now(UTC),
    )


def _report() -> EvalReport:
    """Builds a report that passes the gate.

    Returns:
        EvalReport: the report.
    """
    return EvalReport(
        agent_id=_AGENT_ID,
        agent_version_id=uuid4(),
        version_number=2,
        threshold_percent=80,
        minimum_cases=8,
        total_cases=10,
        passed_cases=9,
        pass_percent=90.0,
        passes_gate=True,
        outcomes=[],
    )


def _published_detail() -> AgentDetail:
    """Builds a published agent.

    Returns:
        AgentDetail: the agent with its version.
    """
    now = datetime.now(UTC)
    agent = Agent(
        id=_AGENT_ID,
        name="Asistente",
        description="Facturas",
        owner_area="Servicio",
        creator="Ana",
        status=AgentStatus.PUBLISHED,
        kind=AgentKind.USER,
        active_version_number=1,
        created_at=now,
        updated_at=now,
    )
    version = AgentVersion(
        id=uuid4(),
        agent_id=_AGENT_ID,
        version_number=1,
        spec=AgentSpec(purpose="Facturas", system_prompt="Eres útil", model_id=uuid4()),
        designer_justification=None,
        created_at=now,
    )
    return AgentDetail(agent=agent, active_version=version)


def test_manual_case_answers_201_and_reaches_the_vertical(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies what the person wrote is what gets stored, for the agent of the path."""
    calls = []
    monkeypatch.setattr(
        evals_router,
        "add_manual_case",
        lambda _session, agent_id, draft: calls.append((agent_id, draft)) or _case(),
    )
    body = {"input": "¿Saldo?", "expected_behavior": "Informa el saldo"}

    response = client.post(f"/agents/{_AGENT_ID}/eval-cases", json=body)

    assert response.status_code == 201
    assert calls[0][0] == _AGENT_ID
    assert calls[0][1].expected_behavior == "Informa el saldo"
    assert response.json()["origin"] == "manual"


@pytest.mark.parametrize(
    "body",
    [
        {"input": "", "expected_behavior": "Responde"},
        {"input": "Hola", "expected_behavior": ""},
        {"input": "Hola"},
        {"input": "Hola", "expected_behavior": "Responde", "origin": "generated"},
    ],
)
def test_manual_case_rejects_an_incomplete_body(client: TestClient, body: dict[str, str]) -> None:
    """Verifies a case without something to compare is refused, and its origin cannot be forged."""
    assert client.post(f"/agents/{_AGENT_ID}/eval-cases", json=body).status_code == 422


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [(AgentNotFoundError("missing"), 404), (AgentNotEvaluableError("system"), 409)],
)
def test_manual_case_translates_failures(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, error: Exception, expected_status: int
) -> None:
    """Verifies each failure tells the person what happened."""
    monkeypatch.setattr(evals_router, "add_manual_case", _Raiser(error))
    body = {"input": "Hola", "expected_behavior": "Saluda"}

    response = client.post(f"/agents/{_AGENT_ID}/eval-cases", json=body)

    assert response.status_code == expected_status
    assert response.json()["detail"] == str(error)


def test_generate_answers_201_with_the_cases(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the person can review what the agent will be measured on."""
    case = _case()
    monkeypatch.setattr(evals_router, "generate_cases", lambda _engine, _agent_id: [case])

    response = client.post(f"/agents/{_AGENT_ID}/eval-cases/generate")

    assert response.status_code == 201
    assert response.json()[0]["id"] == str(case.id)


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (AgentNotFoundError("missing"), 404),
        (ActiveVersionNotFoundError("no version"), 404),
        (AgentNotEvaluableError("system"), 409),
        (CasesAlreadyGeneratedError("twice"), 409),
        (AgentConfigurationError("stale"), 409),
        (ProviderError("timeout"), 502),
        (NoUsableCasesError("too few"), 502),
    ],
)
def test_generate_translates_failures(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, error: Exception, expected_status: int
) -> None:
    """Verifies a failure of the model is not reported as a mistake of the person's request."""
    monkeypatch.setattr(evals_router, "generate_cases", _Raiser(error))

    response = client.post(f"/agents/{_AGENT_ID}/eval-cases/generate")

    assert response.status_code == expected_status


def test_run_returns_the_report(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies the person sees the standing of the version right after running."""
    monkeypatch.setattr(evals_router, "run_evals", lambda _engine, _agent_id: _report())

    response = client.post(f"/agents/{_AGENT_ID}/evals/run")

    assert response.status_code == 200
    assert response.json()["pass_percent"] == 90.0
    assert response.json()["passes_gate"] is True


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (AgentNotFoundError("missing"), 404),
        (ActiveVersionNotFoundError("no version"), 404),
        (AgentNotEvaluableError("system"), 409),
        (NoEvalCasesError("nothing"), 409),
        (AgentConfigurationError("stale"), 409),
        (ProviderError("timeout"), 502),
        (InvalidEvalJudgementError("contradiction"), 502),
    ],
)
def test_run_translates_failures(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, error: Exception, expected_status: int
) -> None:
    """Verifies a failed judge is never mistaken for a failed agent."""
    monkeypatch.setattr(evals_router, "run_evals", _Raiser(error))

    assert client.post(f"/agents/{_AGENT_ID}/evals/run").status_code == expected_status


def test_get_evals_reads_the_report_and_answers_404_if_the_agent_is_unknown(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies reviewing results costs nothing and a wrong identifier is told apart."""
    monkeypatch.setattr(evals_router, "get_report", lambda _session, _agent_id: _report())
    assert client.get(f"/agents/{_AGENT_ID}/evals").json()["version_number"] == 2

    monkeypatch.setattr(evals_router, "get_report", _Raiser(AgentNotFoundError("missing")))
    assert client.get(f"/agents/{_AGENT_ID}/evals").status_code == 404


def test_publish_answers_with_the_published_agent(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the person sees the new status."""
    monkeypatch.setattr(
        evals_router, "publish_agent", lambda _session, _agent_id: _published_detail()
    )

    response = client.post(f"/agents/{_AGENT_ID}/publish")

    assert response.status_code == 200
    assert response.json()["agent"]["status"] == "published"


def test_publish_rejection_returns_the_detail_of_the_failing_cases(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the plan's requirement: a rejection says what failed, in a readable body."""
    rejection = PublishRejection(
        message="Passed 7 of 10",
        pass_percent=70.0,
        threshold_percent=80,
        total_cases=10,
        minimum_cases=8,
        failing_cases=[],
    )
    monkeypatch.setattr(evals_router, "publish_agent", _Raiser(PublishRejectedError(rejection)))

    response = client.post(f"/agents/{_AGENT_ID}/publish")

    assert response.status_code == 409
    assert response.json()["detail"]["pass_percent"] == 70.0
    assert response.json()["detail"]["failing_cases"] == []


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (AgentNotFoundError("missing"), 404),
        (ActiveVersionNotFoundError("no version"), 404),
        (AgentNotEvaluableError("system"), 409),
    ],
)
def test_publish_translates_failures(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, error: Exception, expected_status: int
) -> None:
    """Verifies each failure tells the person what happened."""
    monkeypatch.setattr(evals_router, "publish_agent", _Raiser(error))

    assert client.post(f"/agents/{_AGENT_ID}/publish").status_code == expected_status


def test_monitor_samples_production_by_default_and_accepts_another_origin(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies what the review reads by default, and that the sample reaches it."""
    report = DriftReport(
        agent_id=_AGENT_ID,
        evaluated_runs=0,
        passed_runs=0,
        pass_percent=None,
        baseline_pass_percent=None,
        drift_points=None,
        threshold_percent=80,
        is_drifting=False,
        runs=[],
    )
    calls = []
    monkeypatch.setattr(
        evals_router,
        "monitor_agent",
        lambda _engine, _agent_id, origin, size: calls.append((origin, size)) or report,
    )

    assert client.post(f"/agents/{_AGENT_ID}/evals/monitor").status_code == 200
    client.post(f"/agents/{_AGENT_ID}/evals/monitor?origin=playground&sample_size=3")

    assert calls == [(RunOrigin.PRODUCTION, 10), (RunOrigin.PLAYGROUND, 3)]


@pytest.mark.parametrize("sample_size", [0, 51])
def test_monitor_limits_the_sample(client: TestClient, sample_size: int) -> None:
    """Verifies a typo cannot pay for an unbounded number of judge calls."""
    url = f"/agents/{_AGENT_ID}/evals/monitor?sample_size={sample_size}"

    assert client.post(url).status_code == 422


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (AgentNotFoundError("missing"), 404),
        (ActiveVersionNotFoundError("no version"), 404),
        (AgentNotEvaluableError("system"), 409),
        (AgentConfigurationError("stale"), 409),
        (ProviderError("timeout"), 502),
        (InvalidEvalJudgementError("contradiction"), 502),
    ],
)
def test_monitor_translates_failures(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, error: Exception, expected_status: int
) -> None:
    """Verifies a failed review is never reported as no drift."""
    monkeypatch.setattr(evals_router, "monitor_agent", _Raiser(error))

    assert client.post(f"/agents/{_AGENT_ID}/evals/monitor").status_code == expected_status


def test_evals_routes_require_the_shared_password() -> None:
    """Verifies the new routes, which spend money, are protected."""
    assert TestClient(app).post(f"/agents/{_AGENT_ID}/evals/run").status_code == 401
