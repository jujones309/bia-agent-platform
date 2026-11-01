from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, Engine

from bia.agents.artifacts import AgentSpec
from bia.agents.repository import ActiveVersionNotFoundError
from bia.catalog.tools.artifacts import ToolName
from bia.catalog.tools.sync import sync_tools
from bia.database.connection import database_session
from bia.database.migrate import apply_schema, apply_seeds
from bia.providers.artifacts import ToolCall
from bia.rag import ingestion, retrieval
from bia.rag.artifacts import DocumentDraft, DocumentType, KnowledgeBaseDraft
from bia.rag.ingestion import ingest_document
from bia.rag.repository import insert_knowledge_base
from bia.runtime import runner as runner_module
from bia.runtime.execution import AgentConfigurationError, load_agent_execution
from bia.runtime.runner import run_agent
from bia.tracing.artifacts import RunOrigin, RunStatus, StepType
from bia.tracing.repository import list_runs
from tests.providers.fake import FakeModelProvider
from tests.tracing.seed import insert_active_version, insert_agent, insert_model


@pytest.fixture
def connection(integration_engine: Engine) -> Iterator[Connection]:
    """Provides a connection with the schema and synced tools, rolled back at the end.

    Args:
        integration_engine: The engine of the real database.

    Returns:
        Iterator[Connection]: yields the connection inside the open transaction.
    """
    with integration_engine.connect() as open_connection:
        transaction = open_connection.begin()
        with database_session(open_connection) as session:
            apply_schema(session)
            sync_tools(session)
        yield open_connection
        transaction.rollback()


def _new_agent(connection: Connection, model_id: UUID, tool_names: list[str]) -> UUID:
    """Creates an agent whose active version has the given references.

    Args:
        connection: The connection of the test's transaction.
        model_id: The model of the spec.
        tool_names: The tools of the spec.

    Returns:
        UUID: the identifier of the agent.
    """
    agent_id = insert_agent(connection)
    spec = AgentSpec(
        purpose="Facturas", system_prompt="Eres útil", model_id=model_id, tool_names=tool_names
    )
    insert_active_version(connection, agent_id, spec.model_dump_json())
    return agent_id


def test_load_resolves_the_references_of_the_active_version(connection: Connection) -> None:
    """Verifies the spec stored as JSON resolves to its catalog entries."""
    model_id = insert_model(connection)
    agent_id = _new_agent(connection, model_id, ["consultar_factura"])

    with database_session(connection) as session:
        execution = load_agent_execution(session, agent_id)

    assert execution.version.agent_id == agent_id
    assert execution.model.id == model_id
    assert [tool.name for tool in execution.tools] == ["consultar_factura"]


def test_load_rejects_an_agent_without_an_active_version(connection: Connection) -> None:
    """Verifies both an unknown agent and one with no version cannot be executed."""
    without_version = insert_agent(connection)

    with database_session(connection) as session:
        for agent_id in (without_version, uuid4()):
            with pytest.raises(ActiveVersionNotFoundError, match=str(agent_id)):
                load_agent_execution(session, agent_id)


def test_load_rejects_references_that_are_not_available(connection: Connection) -> None:
    """Verifies a stale spec fails naming the problem, before any tokens are spent."""
    with_retired_tool = _new_agent(connection, insert_model(connection), ["retirada"])
    missing_model_id = uuid4()
    with_missing_model = _new_agent(connection, missing_model_id, [])

    with database_session(connection) as session:
        with pytest.raises(AgentConfigurationError, match="retirada"):
            load_agent_execution(session, with_retired_tool)
        with pytest.raises(AgentConfigurationError, match=str(missing_model_id)):
            load_agent_execution(session, with_missing_model)


def test_run_agent_leaves_the_complete_trace_in_the_database(
    connection: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the whole path on real SQL: steps, summed totals and the tool's reference."""
    agent_id = _new_agent(connection, insert_model(connection), ["consultar_factura"])
    provider = FakeModelProvider()
    provider.queue_tool_calls([_tool_call('{"numero_cliente": "100001"}')])
    provider.queue_text("Listo")
    monkeypatch.setattr(runner_module, "get_provider", lambda _name: provider)

    result = run_agent(connection, agent_id, "saldo", RunOrigin.PLAYGROUND)

    with database_session(connection) as session:
        run = list_runs(session, agent_id, limit=1)[0]
    assert run.id == result.run_id
    assert run.status is RunStatus.SUCCEEDED
    assert run.total_tokens == 30  # two model calls of 15 tokens
    assert [step.step_order for step in run.steps] == [1, 2, 3]
    assert run.steps[1].tool_id is not None


def test_run_agent_stores_the_reason_of_a_failure(
    connection: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies a run that reached its limit is closed with the reason, on real SQL."""
    agent_id = insert_agent(connection)
    spec = AgentSpec(
        purpose="Facturas",
        system_prompt="Eres útil",
        model_id=insert_model(connection),
        tool_names=["consultar_factura"],
        max_iterations=1,
    )
    insert_active_version(connection, agent_id, spec.model_dump_json())
    provider = FakeModelProvider()
    provider.queue_tool_calls([_tool_call("{}")])
    monkeypatch.setattr(runner_module, "get_provider", lambda _name: provider)

    run_agent(connection, agent_id, "saldo", RunOrigin.EVAL)

    with database_session(connection) as session:
        run = list_runs(session, agent_id, limit=1)[0]
    assert run.status is RunStatus.FAILED
    assert "limit of 1 iterations" in run.error
    assert run.steps[1].error is not None


def _new_knowledge_base(connection: Connection, title: str, content: str) -> UUID:
    """Creates a knowledge base holding one tariff document.

    Args:
        connection: The connection of the test's transaction.
        title: The title of the document.
        content: The markdown of the document.

    Returns:
        UUID: the identifier of the base.
    """
    with database_session(connection) as session:
        draft = KnowledgeBaseDraft(name=title, description="Pruebas")
        base_id = insert_knowledge_base(session, draft).id
    document = DocumentDraft(title=title, document_type=DocumentType.TARIFF, content=content)
    ingest_document(connection, base_id, document)
    return base_id


def test_retrieval_reads_only_the_base_of_the_spec_and_leaves_its_step_in_the_trace(
    connection: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the whole path on real SQL: tool, search, trace with chunks and summed cost."""
    with database_session(connection) as session:
        apply_seeds(session)
    embedder = FakeModelProvider(embedding_dimensions=1536)
    monkeypatch.setattr(ingestion, "get_provider", lambda _name: embedder)
    monkeypatch.setattr(retrieval, "get_provider", lambda _name: embedder)
    own_base = _new_knowledge_base(connection, "Propia", "# Hogar\nEstrato 1: 412")
    _new_knowledge_base(connection, "Ajena", "# Secreto\nNo debe aparecer")
    agent_id = insert_agent(connection)
    spec = AgentSpec(
        purpose="Tarifas",
        system_prompt="Eres útil",
        model_id=insert_model(connection),
        tool_names=[ToolName.BUSCAR_CONOCIMIENTO],
        knowledge_base_id=own_base,
    )
    insert_active_version(connection, agent_id, spec.model_dump_json())
    chat = FakeModelProvider()
    chat.queue_tool_calls(
        [
            ToolCall(
                id="call-1",
                name=ToolName.BUSCAR_CONOCIMIENTO,
                arguments='{"consulta": "Hogar\\n\\nEstrato 1: 412"}',
            )
        ]
    )
    chat.queue_text("El estrato 1 paga 412, según Propia.")
    monkeypatch.setattr(runner_module, "get_provider", lambda _name: chat)

    result = run_agent(connection, agent_id, "¿Cuánto paga el estrato 1?", RunOrigin.PLAYGROUND)

    with database_session(connection) as session:
        run = list_runs(session, agent_id, limit=1)[0]
    assert result.status is RunStatus.SUCCEEDED
    step = run.steps[1]
    assert step.step_type is StepType.RETRIEVAL
    assert step.tool_id is not None
    assert step.model_id is not None
    assert [chunk["document"] for chunk in step.output["chunks"]] == ["Propia"]
    assert step.output["chunks"][0]["similarity"] > 0.99
    assert step.cost > 0
    assert run.total_tokens == 31  # two model calls of 15 tokens and a one-text embedding
    assert "Estrato 1: 412" in chat.chat_requests[1][-1].content
    assert "No debe aparecer" not in chat.chat_requests[1][-1].content


def _tool_call(arguments: str) -> ToolCall:
    """Builds a call to the invoice tool.

    Args:
        arguments: The raw JSON arguments.

    Returns:
        ToolCall: the call.
    """
    return ToolCall(id="call-1", name="consultar_factura", arguments=arguments)
