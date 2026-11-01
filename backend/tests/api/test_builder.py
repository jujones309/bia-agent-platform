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
from bia.agents.repository import ActiveVersionNotFoundError
from bia.agents.validation import InvalidAgentSpecError
from bia.api import builder as builder_router
from bia.api.dependencies import get_database_engine
from bia.api.main import app
from bia.builder.artifacts import (
    DesignerJustification,
    DuplicateCandidate,
    DuplicateCheckResult,
    DuplicateVerdict,
    ProposedAgent,
)
from bia.builder.designer.designer import InvalidProposalError
from bia.builder.duplicates.judge import InvalidJudgeDecisionError
from bia.catalog.models.repository import EmbeddingModelUnavailableError
from bia.providers.base import ProviderError
from bia.runtime.execution import AgentConfigurationError

_PROPOSE_BODY = {"description": "Dudas de facturas", "owner_area": "Servicio", "creator": "Ana"}


@pytest.fixture
def client(api_client: TestClient) -> TestClient:
    """Provides an authenticated client that never reaches a real database.

    Args:
        api_client: The authenticated client.

    Returns:
        TestClient: the client.
    """
    app.dependency_overrides[get_database_engine] = lambda: None
    return api_client


class _Raiser:
    """Stands for a builder function that fails; a class because nested functions are banned."""

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


def _proposed_agent() -> ProposedAgent:
    """Builds the outcome of a proposal.

    Returns:
        ProposedAgent: the outcome.
    """
    now = datetime.now(UTC)
    agent_id = uuid4()
    agent = Agent(
        id=agent_id,
        name="Asistente",
        description="Dudas de facturas",
        owner_area="Servicio",
        creator="Ana",
        status=AgentStatus.DRAFT,
        kind=AgentKind.USER,
        active_version_number=1,
        created_at=now,
        updated_at=now,
    )
    version = AgentVersion(
        id=uuid4(),
        agent_id=agent_id,
        version_number=1,
        spec=AgentSpec(purpose="Facturas", system_prompt="Eres útil", model_id=uuid4()),
        designer_justification="model: Es barato",
        created_at=now,
    )
    justification = DesignerJustification(
        model="Es barato", tools="Ninguna", knowledge_base="Ninguna", guardrails="Evita"
    )
    return ProposedAgent(
        agent=AgentDetail(agent=agent, active_version=version), justification=justification
    )


def test_check_returns_the_verdict_and_the_candidate(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the need reaches the judge and the person gets the agent to confirm."""
    candidate = DuplicateCandidate(
        agent_id=uuid4(), name="Asistente", description="Facturas", similarity=0.9
    )
    result = DuplicateCheckResult(
        verdict=DuplicateVerdict.EXISTS, candidate=candidate, reason="Cubre la necesidad"
    )
    requests = []
    monkeypatch.setattr(
        builder_router,
        "check_duplicates",
        lambda _engine, request: requests.append(request) or result,
    )

    response = client.post("/builder/check", json={"description": "Dudas de facturas"})

    assert response.status_code == 200
    assert requests[0].description == "Dudas de facturas"
    body = response.json()
    assert body["verdict"] == "exists"
    assert body["candidate"]["agent_id"] == str(candidate.agent_id)
    assert body["reason"] == "Cubre la necesidad"


def test_check_rejects_an_empty_description(client: TestClient) -> None:
    """Verifies nothing is paid for comparing an empty need."""
    assert client.post("/builder/check", json={"description": ""}).status_code == 422


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (ProviderError("timeout"), 502),
        (InvalidJudgeDecisionError("invented"), 502),
        (ActiveVersionNotFoundError("not registered"), 503),
        (AgentConfigurationError("retired tool"), 503),
        (EmbeddingModelUnavailableError("no model"), 503),
    ],
)
def test_check_translates_failures_and_never_answers_not_exists(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected_status: int,
) -> None:
    """Verifies a failed check is visible, since reading it as no duplicate would create one."""
    monkeypatch.setattr(builder_router, "check_duplicates", _Raiser(error))

    response = client.post("/builder/check", json={"description": "Dudas"})

    assert response.status_code == expected_status
    assert response.json()["detail"] == str(error)


def test_propose_answers_201_with_the_draft_and_its_reasons(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the owner reaches the designer, and the response has what the person reviews."""
    proposed = _proposed_agent()
    requests = []
    monkeypatch.setattr(
        builder_router,
        "propose_agent",
        lambda _engine, request: requests.append(request) or proposed,
    )

    response = client.post("/builder/propose", json=_PROPOSE_BODY)

    assert response.status_code == 201
    assert (requests[0].owner_area, requests[0].creator) == ("Servicio", "Ana")
    body = response.json()
    assert body["agent"]["agent"]["status"] == "draft"
    assert body["agent"]["active_version"]["designer_justification"] == "model: Es barato"
    assert body["justification"]["model"] == "Es barato"


@pytest.mark.parametrize("missing", ["description", "owner_area", "creator"])
def test_propose_requires_the_need_and_its_owner(client: TestClient, missing: str) -> None:
    """Verifies no agent can be designed without knowing whose it is."""
    body = {key: value for key, value in _PROPOSE_BODY.items() if key != missing}

    assert client.post("/builder/propose", json=body).status_code == 422


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (ProviderError("timeout"), 502),
        (InvalidProposalError("no valid spec"), 502),
        (InvalidAgentSpecError("the catalog changed"), 502),
        (ActiveVersionNotFoundError("not registered"), 503),
        (AgentConfigurationError("retired model"), 503),
        (EmbeddingModelUnavailableError("no model"), 503),
    ],
)
def test_propose_translates_failures(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected_status: int,
) -> None:
    """Verifies a failure of the designer is not reported as a mistake of the person's request."""
    monkeypatch.setattr(builder_router, "propose_agent", _Raiser(error))

    response = client.post("/builder/propose", json=_PROPOSE_BODY)

    assert response.status_code == expected_status
    assert response.json()["detail"] == str(error)


def test_builder_routes_require_the_shared_password() -> None:
    """Verifies the new routes, which spend money, are protected."""
    assert TestClient(app).post("/builder/check", json={"description": "x"}).status_code == 401
