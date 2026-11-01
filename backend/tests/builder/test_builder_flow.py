from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

import pytest
from sqlalchemy import Connection, Engine
from sqlalchemy.orm import Session

from bia.agents import registry as registry_module
from bia.agents.artifacts import AgentKind, AgentStatus
from bia.agents.repository import get_active_version, get_agent
from bia.builder import system_run
from bia.builder.artifacts import (
    AgentDesign,
    AgentProposalRequest,
    AgentRequest,
    DesignerJustification,
    DuplicateVerdict,
    JudgeDecision,
)
from bia.builder.designer import designer as designer_module
from bia.builder.designer.designer import propose_agent
from bia.builder.duplicates.judge import check_duplicates
from bia.builder.system_agents import (
    DESIGNER_AGENT_ID,
    DUPLICATE_JUDGE_AGENT_ID,
    sync_system_agents,
)
from bia.catalog.models.artifacts import ModelSize
from bia.catalog.models.repository import list_catalog_models
from bia.catalog.tools.sync import sync_tools
from bia.database.connection import database_session
from bia.database.migrate import apply_schema, apply_seeds
from bia.rag.artifacts import KnowledgeBaseDraft
from bia.rag.repository import insert_knowledge_base
from bia.tracing.artifacts import RunOrigin, RunStatus
from bia.tracing.repository import list_runs
from tests.builder.duplicates.seed import hide_published_agents, insert_registered_agent
from tests.providers.fake import FakeModelProvider

_EMBEDDING_DIMENSIONS = 1536
_NEED = "Un bot que responda dudas de facturas"
_JUSTIFICATION = DesignerJustification(
    model="Es barato", tools="Busca", knowledge_base="Es la de facturas", guardrails="Evita"
)


@pytest.fixture
def connection(integration_engine: Engine) -> Iterator[Connection]:
    """Provides a connection with a complete registry and catalogs, rolled back at the end.

    Args:
        integration_engine: The engine of the real database.

    Returns:
        Iterator[Connection]: yields the connection inside the open transaction.
    """
    with integration_engine.connect() as open_connection:
        transaction = open_connection.begin()
        with database_session(open_connection) as session:
            apply_schema(session)
            apply_seeds(session)
            sync_tools(session)
            sync_system_agents(session)
        hide_published_agents(open_connection)
        yield open_connection
        transaction.rollback()


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> FakeModelProvider:
    """Replaces the provider of the builder and of the registry.

    Args:
        monkeypatch: The patcher of the modules.

    Returns:
        FakeModelProvider: the provider they will use.
    """
    fake = FakeModelProvider(embedding_dimensions=_EMBEDDING_DIMENSIONS)
    monkeypatch.setattr(system_run, "get_provider", lambda _name: fake)
    monkeypatch.setattr(registry_module, "get_provider", lambda _name: fake)
    return fake


@contextmanager
def _savepoint_session(bind: Connection) -> Iterator[Session]:
    """Opens a session whose rollback undoes only its own work.

    Exists because in production each session has its own connection, so a rejected validation
    cannot undo the run; on the one connection of a test, it would undo the whole test.

    Args:
        bind: The connection of the test's transaction.

    Returns:
        Iterator[Session]: yields the session.
    """
    with Session(bind, join_transaction_mode="create_savepoint") as session, session.begin():
        yield session


def _small_model_id(connection: Connection) -> UUID:
    """Finds a model the designer can choose.

    Args:
        connection: The connection of the test's transaction.

    Returns:
        UUID: the identifier of a chat model of the catalog.
    """
    with database_session(connection) as session:
        models = list_catalog_models(session, only_active=True)
    return next(model.id for model in models if model.size is ModelSize.SMALL)


def _design(model_id: UUID, knowledge_base_id: UUID | None, tool_names: list[str]) -> AgentDesign:
    """Builds an answer of the designer.

    Args:
        model_id: The chosen model.
        knowledge_base_id: The chosen base.
        tool_names: The chosen tools.

    Returns:
        AgentDesign: the answer.
    """
    return AgentDesign(
        name="Asistente de facturación",
        purpose="Facturas",
        system_prompt="Eres útil",
        model_id=model_id,
        tool_names=tool_names,
        knowledge_base_id=knowledge_base_id,
        guardrails=[],
        max_iterations=5,
        justification=_JUSTIFICATION,
    )


def test_check_traces_a_run_of_the_judge_with_search_and_verdict(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies the real search reaches the judge, and the builder appears in its own traces."""
    agent_id = insert_registered_agent(connection, [0.5] * _EMBEDDING_DIMENSIONS)
    provider.queue_structured(
        JudgeDecision(verdict=DuplicateVerdict.EXISTS, candidate_agent_id=agent_id, reason="Cubre")
    )

    result = check_duplicates(connection, AgentRequest(description=_NEED))

    assert result.candidate.agent_id == agent_id
    with database_session(connection) as session:
        run = list_runs(session, DUPLICATE_JUDGE_AGENT_ID, limit=1)[0]
    assert run.origin is RunOrigin.BUILDER
    assert run.status is RunStatus.SUCCEEDED
    assert run.input == _NEED
    assert len(run.steps) == 2
    assert run.total_tokens > 0
    assert run.total_cost > 0


def test_propose_creates_a_draft_user_agent_with_its_justification(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies the whole path: a reviewable draft, and a traced designer."""
    with database_session(connection) as session:
        base = insert_knowledge_base(session, KnowledgeBaseDraft(name="Base", description="Datos"))
    design = _design(_small_model_id(connection), base.id, ["buscar_conocimiento"])
    provider.queue_structured(design)
    request = AgentProposalRequest(description=_NEED, owner_area="Servicio", creator="Ana")

    proposed = propose_agent(connection, request)

    agent_id = proposed.agent.agent.id
    with database_session(connection) as session:
        agent = get_agent(session, agent_id)
        version = get_active_version(session, agent_id)
        designer_run = list_runs(session, DESIGNER_AGENT_ID, limit=1)[0]
    assert (agent.status, agent.kind) == (AgentStatus.DRAFT, AgentKind.USER)
    assert agent.name == "Asistente de facturación"
    assert agent.description == _NEED
    assert (agent.owner_area, agent.creator) == ("Servicio", "Ana")
    assert version.spec.knowledge_base_id == base.id
    assert version.designer_justification.splitlines()[0] == "model: Es barato"
    assert designer_run.status is RunStatus.SUCCEEDED
    assert '"name"' in provider.chat_requests[0][1].content
    assert str(base.id) in provider.chat_requests[0][1].content


def test_propose_rejects_invented_references_against_the_real_catalog(
    connection: Connection, provider: FakeModelProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the real validation drives the retry: an embedding model is not a choice."""
    monkeypatch.setattr(designer_module, "database_session", _savepoint_session)
    with database_session(connection) as session:
        models = list_catalog_models(session, only_active=True)
    embedding_model = next(model.id for model in models if model.size is ModelSize.EMBEDDING)
    provider.queue_structured(_design(embedding_model, None, []))
    provider.queue_structured(_design(_small_model_id(connection), None, []))
    request = AgentProposalRequest(description=_NEED, owner_area="Servicio", creator="Ana")

    proposed = propose_agent(connection, request)

    assert "only generates embeddings" in provider.chat_requests[1][-1].content
    assert proposed.agent.active_version.spec.model_id != embedding_model
