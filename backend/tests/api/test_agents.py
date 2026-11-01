from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from bia.agents.artifacts import (
    Agent,
    AgentDetail,
    AgentKind,
    AgentSpec,
    AgentSpecPatch,
    AgentStatus,
    AgentVersion,
)
from bia.agents.registry import AgentNotManageableError, UnchangedAgentIdentityError
from bia.agents.repository import (
    ActiveVersionNotFoundError,
    AgentNotFoundError,
    AgentVersionNotFoundError,
)
from bia.agents.validation import InvalidAgentSpecError
from bia.api import agents as agents_router
from bia.api.dependencies import get_database_engine, get_session
from bia.api.main import app
from bia.catalog.models.repository import EmbeddingModelUnavailableError
from bia.providers.base import ProviderError


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
    """Stands for a registry function that fails; a class because nested functions are banned."""

    def __init__(self, error: Exception) -> None:
        """Keeps the error.

        Args:
            error (Exception): The error to raise when called.
        """
        self._error = error

    def __call__(self, *_args: object) -> AgentDetail:
        """Raises the kept error.

        Args:
            _args: The unused arguments of the replaced function.

        Returns:
            AgentDetail: never.

        Raises:
            Exception: The kept error.
        """
        raise self._error


def _detail() -> AgentDetail:
    """Builds an agent at its first version.

    Returns:
        AgentDetail: the agent and its version.
    """
    now = datetime.now(UTC)
    agent = Agent(
        id=uuid4(),
        name="Asistente",
        description="Responde facturas",
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
        agent_id=agent.id,
        version_number=1,
        spec=AgentSpec(purpose="Facturas", system_prompt="Eres útil", model_id=uuid4()),
        designer_justification=None,
        created_at=now,
    )
    return AgentDetail(agent=agent, active_version=version)


def _create_body() -> dict[str, object]:
    """Builds a valid body for `POST /agents`.

    Returns:
        dict[str, object]: the body.
    """
    return {
        "name": "Asistente",
        "description": "Responde facturas",
        "owner_area": "Servicio",
        "creator": "Ana",
        "spec": {"purpose": "Facturas", "system_prompt": "Eres útil", "model_id": str(uuid4())},
    }


def test_create_answers_201_with_the_agent_and_its_version(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the body reaches the registry and the caller gets the spec back."""
    detail = _detail()
    drafts = []
    monkeypatch.setattr(
        agents_router, "create_agent", lambda _bind, draft: drafts.append(draft) or detail
    )

    response = client.post("/agents", json=_create_body())

    assert response.status_code == 201
    assert response.json()["agent"]["id"] == str(detail.agent.id)
    assert response.json()["active_version"]["version_number"] == 1
    assert drafts[0].owner_area == "Servicio"


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (InvalidAgentSpecError("modelo inventado"), 422),
        (ProviderError("se cayó"), 502),
        (EmbeddingModelUnavailableError("sin modelo"), 503),
    ],
)
def test_create_explains_why_it_could_not_register_the_agent(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, error: Exception, expected_status: int
) -> None:
    """Verifies each failure is the caller's or an upstream one, and never an opaque 500."""
    monkeypatch.setattr(agents_router, "create_agent", _Raiser(error))

    response = client.post("/agents", json=_create_body())

    assert response.status_code == expected_status
    assert response.json()["detail"] == str(error)


@pytest.mark.parametrize(
    "changes",
    [
        {"name": ""},
        {"description": ""},
        {"kind": "system"},
        {"status": "published"},
    ],
)
def test_create_rejects_empty_identity_and_fields_the_caller_cannot_choose(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, changes: dict[str, str]
) -> None:
    """Verifies nobody can create a published or system agent by adding a field to the body."""
    monkeypatch.setattr(agents_router, "create_agent", _Raiser(AssertionError("must not run")))

    assert client.post("/agents", json={**_create_body(), **changes}).status_code == 422


def test_list_returns_the_agents_without_their_embedding(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the inventory shows identities and does not leak internal vectors."""
    detail = _detail()
    monkeypatch.setattr(agents_router, "list_agents", lambda _session: [detail.agent])

    body = client.get("/agents").json()

    assert [agent["id"] for agent in body] == [str(detail.agent.id)]
    assert "description_embedding" not in body[0]


def test_get_answers_404_for_an_unknown_agent(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies a wrong identifier explains itself."""
    error = AgentNotFoundError("no existe")
    monkeypatch.setattr(agents_router, "get_agent_detail", _Raiser(error))

    response = client.get(f"/agents/{uuid4()}")

    assert (response.status_code, response.json()["detail"]) == (404, "no existe")


def test_patch_sends_only_the_fields_of_the_request(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies omitted fields stay unset, which is what keeps their value in the new version."""
    agent_id = uuid4()
    calls: list[tuple[object, AgentSpecPatch]] = []
    detail = _detail()
    monkeypatch.setattr(
        agents_router,
        "add_version",
        lambda _session, *args: calls.append(args) or detail,
    )

    response = client.patch(f"/agents/{agent_id}", json={"guardrails": ["No inventes"]})

    assert response.status_code == 200
    assert calls[0][0] == agent_id
    assert calls[0][1].model_fields_set == {"guardrails"}


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (AgentNotFoundError("no existe"), 404),
        (ActiveVersionNotFoundError("sin versión"), 404),
        (InvalidAgentSpecError("herramienta inventada"), 422),
    ],
)
def test_patch_explains_why_it_could_not_create_the_version(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, error: Exception, expected_status: int
) -> None:
    """Verifies each failure of an edit reaches the caller with its reason."""
    monkeypatch.setattr(agents_router, "add_version", _Raiser(error))

    response = client.patch(f"/agents/{uuid4()}", json={"purpose": "Otro"})

    assert response.status_code == expected_status
    assert response.json()["detail"] == str(error)


def test_patch_rejects_fields_outside_the_spec(client: TestClient) -> None:
    """Verifies a misspelled setting or an identity field is not silently ignored."""
    response = client.patch(f"/agents/{uuid4()}", json={"temperature": 0.2})

    assert response.status_code == 422


def test_versions_answers_404_for_an_unknown_agent_instead_of_an_empty_list(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies a wrong identifier is not mistaken for an agent without history."""
    monkeypatch.setattr(agents_router, "get_agent", _Raiser(AgentNotFoundError("no existe")))
    monkeypatch.setattr(agents_router, "list_versions", lambda *_args: [])

    assert client.get(f"/agents/{uuid4()}/versions").status_code == 404


def test_versions_returns_the_history(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies the history can be read to choose a version to roll back to."""
    detail = _detail()
    monkeypatch.setattr(agents_router, "get_agent", lambda *_args: detail.agent)
    monkeypatch.setattr(agents_router, "list_versions", lambda *_args: [detail.active_version])

    body = client.get(f"/agents/{detail.agent.id}/versions").json()

    assert [version["version_number"] for version in body] == [1]


def test_activate_passes_the_number_of_the_path(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the rollback targets the version the caller named."""
    agent_id = uuid4()
    calls = []
    detail = _detail()
    monkeypatch.setattr(
        agents_router,
        "activate_version",
        lambda _session, *args: calls.append(args) or detail,
    )

    response = client.post(f"/agents/{agent_id}/versions/3/activate")

    assert response.status_code == 200
    assert calls == [(agent_id, 3)]


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (AgentNotFoundError("no existe"), 404),
        (AgentVersionNotFoundError("no hay versión"), 404),
        (InvalidAgentSpecError("herramienta retirada"), 409),
    ],
)
def test_activate_explains_why_it_could_not_roll_back(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, error: Exception, expected_status: int
) -> None:
    """Verifies a stored version that cannot run is a conflict, not a bad request body."""
    monkeypatch.setattr(agents_router, "activate_version", _Raiser(error))

    response = client.post(f"/agents/{uuid4()}/versions/1/activate")

    assert response.status_code == expected_status
    assert response.json()["detail"] == str(error)


def test_agents_endpoints_require_credentials() -> None:
    """Verifies the registry stays behind the shared password."""
    assert TestClient(app).get("/agents").status_code == 401


def test_archive_answers_with_the_archived_agent(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the route archives the agent in the path and returns what the registry says."""
    detail = _detail()
    archived = []
    monkeypatch.setattr(
        agents_router,
        "archive_agent",
        lambda _session, agent_id: archived.append(agent_id) or detail,
    )

    response = client.post(f"/agents/{detail.agent.id}/archive")

    assert response.status_code == 200
    assert response.json()["agent"]["id"] == str(detail.agent.id)
    assert archived == [detail.agent.id]


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (AgentNotFoundError("There is no agent"), 404),
        (AgentNotManageableError("It is a part of the platform"), 409),
    ],
)
def test_archive_translates_each_failure(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected_status: int,
) -> None:
    """Verifies each failure reaches the person with its own status and reason."""
    monkeypatch.setattr(agents_router, "archive_agent", _Raiser(error))

    response = client.post(f"/agents/{uuid4()}/archive")

    assert response.status_code == expected_status
    assert response.json()["detail"] == str(error)


def test_identity_reaches_the_registry_with_only_what_was_sent(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the body arrives as a partial change."""
    detail = _detail()
    patches = []
    monkeypatch.setattr(
        agents_router,
        "update_identity",
        lambda _engine, _agent_id, patch: patches.append(patch) or detail,
    )

    response = client.patch(f"/agents/{detail.agent.id}/identity", json={"name": "Nuevo"})

    assert response.status_code == 200
    assert patches[0].model_dump(exclude_none=True) == {"name": "Nuevo"}


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (AgentNotFoundError("There is no agent"), 404),
        (ActiveVersionNotFoundError("It has no version"), 404),
        (AgentNotManageableError("It is archived"), 409),
        (UnchangedAgentIdentityError("Nothing changes"), 422),
        (ProviderError("Provider down"), 502),
        (EmbeddingModelUnavailableError("No embedding model"), 503),
    ],
)
def test_identity_translates_each_failure(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected_status: int,
) -> None:
    """Verifies each failure reaches the person with its own status and reason."""
    monkeypatch.setattr(agents_router, "update_identity", _Raiser(error))

    response = client.patch(f"/agents/{uuid4()}/identity", json={"name": "Nuevo"})

    assert response.status_code == expected_status
    assert response.json()["detail"] == str(error)


def test_identity_rejects_a_blank_name_and_the_creator(client: TestClient) -> None:
    """Verifies the contract stops both before reaching the registry."""
    agent_id = uuid4()

    assert client.patch(f"/agents/{agent_id}/identity", json={"name": " "}).status_code == 422
    assert client.patch(f"/agents/{agent_id}/identity", json={"creator": "X"}).status_code == 422
