from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, Engine, Uuid, column, select, table, update

from bia.agents import registry as registry_module
from bia.agents.artifacts import AgentDraft, AgentKind, AgentSpec, AgentSpecPatch, AgentStatus
from bia.agents.registry import (
    activate_version,
    add_version,
    create_agent,
    get_agent_detail,
)
from bia.agents.repository import (
    AgentNotFoundError,
    AgentVersionNotFoundError,
    list_agents,
    list_versions,
    set_agent_status,
)
from bia.agents.validation import InvalidAgentSpecError
from bia.builder.system_agents import EVAL_JUDGE_AGENT_ID, sync_system_agents
from bia.catalog.models.repository import EmbeddingModelUnavailableError
from bia.catalog.tools.sync import sync_tools
from bia.database.connection import database_session
from bia.database.migrate import apply_schema, apply_seeds
from bia.providers.base import ProviderError
from bia.rag.artifacts import KnowledgeBaseDraft
from bia.rag.repository import insert_knowledge_base
from bia.runtime.execution import load_agent_execution
from bia.tracing.artifacts import RunOrigin, RunStatus, StepType
from bia.tracing.repository import list_runs
from tests.providers.fake import FakeModelProvider
from tests.tracing.seed import insert_model

_EMBEDDING_DIMENSIONS = 1536
_MODELS = table("models", column("id", Uuid), column("size"), column("is_active"))
_TOOLS = table("tools", column("name"), column("is_active"))
_AGENTS = table("agents", column("id", Uuid), column("description_embedding"))


@pytest.fixture
def connection(integration_engine: Engine) -> Iterator[Connection]:
    """Provides a connection with the schema, the seeded catalog and synced tools, rolled back.

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
        yield open_connection
        transaction.rollback()


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> FakeModelProvider:
    """Replaces the provider of the registry with one that embeds at the real dimensions.

    Args:
        monkeypatch: The patcher of the registry module.

    Returns:
        FakeModelProvider: the provider the registry will use.
    """
    fake = FakeModelProvider(embedding_dimensions=_EMBEDDING_DIMENSIONS)
    monkeypatch.setattr(registry_module, "get_provider", lambda _name: fake)
    return fake


def _draft(model_id: UUID, tool_names: list[str] | None = None) -> AgentDraft:
    """Builds a request to create an agent.

    Args:
        model_id: The model of the spec.
        tool_names: The tools of the spec.

    Returns:
        AgentDraft: the draft.
    """
    spec = AgentSpec(
        purpose="Facturas",
        system_prompt="Eres útil",
        model_id=model_id,
        tool_names=tool_names or [],
    )
    return AgentDraft(
        name="Asistente",
        description="Responde dudas de facturas",
        owner_area="Servicio al cliente",
        creator="Ana",
        spec=spec,
    )


def _new_agent(connection: Connection) -> UUID:
    """Creates an agent through the registry; requires the `provider` fixture.

    Args:
        connection: The connection of the test's transaction.

    Returns:
        UUID: the identifier of the agent.
    """
    return create_agent(connection, _draft(insert_model(connection))).agent.id


def _count_agents(connection: Connection) -> int:
    """Counts the agents in the database.

    Args:
        connection: The connection of the test's transaction.

    Returns:
        int: the number of agents.
    """
    with database_session(connection) as session:
        return len(list_agents(session))


def test_create_registers_a_draft_user_agent_at_version_1(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies the initial state of the lifecycle, and that the spec survives its storage."""
    draft = _draft(insert_model(connection), ["consultar_factura"])

    detail = create_agent(connection, draft)

    assert detail.agent.status is AgentStatus.DRAFT
    assert detail.agent.kind is AgentKind.USER
    assert detail.agent.active_version_number == 1
    assert detail.active_version.version_number == 1
    assert detail.active_version.designer_justification is None
    with database_session(connection) as session:
        assert get_agent_detail(session, detail.agent.id).active_version.spec == draft.spec


def test_create_makes_the_agent_executable_by_the_runtime(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies registry and runtime agree on what the active version is."""
    model_id = insert_model(connection)
    agent_id = create_agent(connection, _draft(model_id, ["consultar_factura"])).agent.id

    with database_session(connection) as session:
        execution = load_agent_execution(session, agent_id)

    assert execution.model.id == model_id
    assert [tool.name for tool in execution.tools] == ["consultar_factura"]


def test_create_stores_the_embedding_of_the_description(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies duplicate detection will find the vector of this description, from the catalog."""
    agent_id = _new_agent(connection)
    expected = provider.embed(["Responde dudas de facturas"], "any").embeddings[0]

    stored = connection.execute(
        select(_AGENTS.c.description_embedding).where(_AGENTS.c.id == agent_id)
    ).scalar_one()

    assert [round(value, 3) for value in _parse_vector(stored)] == [
        round(value, 3) for value in expected
    ]
    assert provider.requested_models[0] == "text-embedding-3-small"


def test_create_traces_the_embedding_as_a_closed_run_with_its_cost(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies the LLM call of the registry reaches the audit record, without the vector."""
    agent_id = _new_agent(connection)

    with database_session(connection) as session:
        run = list_runs(session, agent_id, limit=5)[0]

    assert run.origin is RunOrigin.BUILDER
    assert run.status is RunStatus.SUCCEEDED
    assert run.total_tokens == 1
    assert run.total_cost > 0
    assert [step.step_type for step in run.steps] == [StepType.LLM_CALL]
    assert run.steps[0].output == {"embedding_dimensions": _EMBEDDING_DIMENSIONS}


def test_create_rejects_an_invalid_spec_without_spending_or_writing(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies the catalog is checked before the embedding, on the real catalog queries."""
    missing_model_id = uuid4()
    draft = _draft(missing_model_id, ["inventada"])
    agents_before = _count_agents(connection)

    with pytest.raises(InvalidAgentSpecError) as caught, connection.begin_nested():
        create_agent(connection, draft)

    assert str(missing_model_id) in str(caught.value)
    assert "inventada" in str(caught.value)
    assert provider.requested_models == []
    assert _count_agents(connection) == agents_before


def test_create_rejects_a_retired_model_and_a_retired_tool(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies inactive catalog entries, read from the database, close new specs."""
    model_id = insert_model(connection)
    connection.execute(update(_MODELS).where(_MODELS.c.id == model_id).values(is_active=False))
    connection.execute(update(_TOOLS).values(is_active=False))

    with pytest.raises(InvalidAgentSpecError) as caught, connection.begin_nested():
        create_agent(connection, _draft(model_id, ["consultar_factura"]))

    assert "is retired" in str(caught.value)
    assert "'consultar_factura' is retired" in str(caught.value)


def test_create_leaves_nothing_behind_if_the_embedding_fails(
    connection: Connection, monkeypatch: pytest.MonkeyPatch, provider: FakeModelProvider
) -> None:
    """Verifies there is no agent without embedding that duplicate detection cannot find."""
    monkeypatch.setattr(provider, "embed", _FailingEmbed())
    agents_before = _count_agents(connection)

    with pytest.raises(ProviderError):
        create_agent(connection, _draft(insert_model(connection)))

    assert _count_agents(connection) == agents_before


def test_create_fails_clearly_without_an_embedding_model(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies a misconfigured catalog stops the creation instead of skipping the embedding."""
    model_id = insert_model(connection)
    connection.execute(update(_MODELS).where(_MODELS.c.size == "embedding").values(is_active=False))

    with pytest.raises(EmbeddingModelUnavailableError), connection.begin_nested():
        create_agent(connection, _draft(model_id))


def test_editing_adds_a_version_and_never_overwrites(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies the old spec stays intact and the agent moves to the new one."""
    agent_id = _new_agent(connection)

    with database_session(connection) as session:
        detail = add_version(session, agent_id, AgentSpecPatch(system_prompt="Sé breve"))
        versions = list_versions(session, agent_id)

    assert detail.agent.active_version_number == 2
    assert detail.active_version.spec.system_prompt == "Sé breve"
    assert [version.version_number for version in versions] == [1, 2]
    assert versions[0].spec.system_prompt == "Eres útil"
    assert versions[1].spec.purpose == versions[0].spec.purpose


def test_editing_validates_the_merged_spec_against_the_catalog(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies an edit cannot sneak in a tool that does not exist, and leaves no version."""
    agent_id = _new_agent(connection)

    with database_session(connection) as session:
        with pytest.raises(InvalidAgentSpecError, match="inventada"):
            add_version(session, agent_id, AgentSpecPatch(tool_names=["inventada"]))
        assert len(list_versions(session, agent_id)) == 1


def test_editing_an_unknown_agent_is_a_clear_error(connection: Connection) -> None:
    """Verifies a wrong identifier does not surface as a database failure."""
    missing_id = uuid4()

    with (
        database_session(connection) as session,
        pytest.raises(AgentNotFoundError, match=str(missing_id)),
    ):
        add_version(session, missing_id, AgentSpecPatch(purpose="Otro"))


def test_rollback_points_the_runtime_at_the_old_version_without_adding_one(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies undoing a change restores the old behavior and keeps the whole history."""
    agent_id = _new_agent(connection)

    with database_session(connection) as session:
        add_version(session, agent_id, AgentSpecPatch(system_prompt="Sé breve"))
        detail = activate_version(session, agent_id, 1)
        execution = load_agent_execution(session, agent_id)
        versions = list_versions(session, agent_id)

    assert detail.agent.active_version_number == 1
    assert execution.version.spec.system_prompt == "Eres útil"
    assert len(versions) == 2


def test_editing_after_a_rollback_builds_on_the_active_version_with_the_next_number(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies numbers never repeat and the discarded change does not come back."""
    agent_id = _new_agent(connection)

    with database_session(connection) as session:
        add_version(session, agent_id, AgentSpecPatch(system_prompt="Mala idea"))
        activate_version(session, agent_id, 1)
        detail = add_version(session, agent_id, AgentSpecPatch(purpose="Otro"))

    assert detail.active_version.version_number == 3
    assert detail.active_version.spec.system_prompt == "Eres útil"


def test_rollback_to_a_missing_version_changes_nothing(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies a wrong number fails instead of leaving the agent without a version to run."""
    agent_id = _new_agent(connection)

    with database_session(connection) as session:
        with pytest.raises(AgentVersionNotFoundError, match="no version 9"):
            activate_version(session, agent_id, 9)
        assert get_agent_detail(session, agent_id).agent.active_version_number == 1


def test_rollback_rejects_a_version_whose_tool_was_retired(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies a rollback cannot leave the agent in a state the runtime refuses to execute."""
    draft = _draft(insert_model(connection), ["consultar_factura"])
    agent_id = create_agent(connection, draft).agent.id
    with database_session(connection) as session:
        add_version(session, agent_id, AgentSpecPatch(tool_names=[]))
    connection.execute(update(_TOOLS).values(is_active=False))

    with (
        database_session(connection) as session,
        pytest.raises(InvalidAgentSpecError, match="consultar_factura"),
    ):
        activate_version(session, agent_id, 1)


def test_rollback_allows_a_version_whose_model_was_retired(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies retiring a model does not block undoing a bad change: the runtime still runs it."""
    old_model_id = insert_model(connection)
    agent_id = create_agent(connection, _draft(old_model_id)).agent.id
    with database_session(connection) as session:
        add_version(session, agent_id, AgentSpecPatch(model_id=insert_model(connection)))
    connection.execute(update(_MODELS).where(_MODELS.c.id == old_model_id).values(is_active=False))

    with database_session(connection) as session:
        detail = activate_version(session, agent_id, 1)

    assert detail.active_version.spec.model_id == old_model_id


def test_a_spec_with_a_real_base_and_the_tool_is_accepted_and_cannot_lose_the_base(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies on real SQL that a stored base passes, and detaching it alone is rejected."""
    with database_session(connection) as session:
        draft = KnowledgeBaseDraft(name="Facturación", description="Tarifas")
        base_id = insert_knowledge_base(session, draft).id
    agent_id = _new_agent(connection)

    with database_session(connection) as session:
        changes = {"tool_names": ["buscar_conocimiento"], "knowledge_base_id": base_id}
        detail = add_version(session, agent_id, AgentSpecPatch(**changes))
        with pytest.raises(InvalidAgentSpecError, match="needs a knowledge_base_id"):
            add_version(session, agent_id, AgentSpecPatch(knowledge_base_id=None))

    assert detail.active_version.spec.knowledge_base_id == base_id


def test_a_spec_with_an_unknown_base_is_rejected(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies the reference is checked against the real table."""
    agent_id = _new_agent(connection)
    missing_id = uuid4()
    changes = {"tool_names": ["buscar_conocimiento"], "knowledge_base_id": missing_id}

    with (
        database_session(connection) as session,
        pytest.raises(InvalidAgentSpecError, match=str(missing_id)),
    ):
        add_version(session, agent_id, AgentSpecPatch(**changes))


def _publish_directly(connection: Connection, agent_id: UUID) -> None:
    """Marks an agent as published, since the gate belongs to the tests of the evals.

    Args:
        connection: The connection of the test's transaction.
        agent_id: The agent to change.

    Returns:
        None: the status is updated.
    """
    with database_session(connection) as session:
        set_agent_status(session, agent_id, AgentStatus.PUBLISHED)


def test_editing_a_published_agent_takes_back_its_publication(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies an untested version cannot keep the status that promises it was tested."""
    agent_id = _new_agent(connection)
    _publish_directly(connection, agent_id)

    with database_session(connection) as session:
        detail = add_version(session, agent_id, AgentSpecPatch(purpose="Otro"))

    assert detail.agent.status is AgentStatus.TESTING
    assert detail.agent.active_version_number == 2


def test_rolling_back_a_published_agent_takes_back_its_publication(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies a rollback also goes through the gate, even if the version is an older one."""
    agent_id = _new_agent(connection)
    with database_session(connection) as session:
        add_version(session, agent_id, AgentSpecPatch(purpose="Otro"))
    _publish_directly(connection, agent_id)

    with database_session(connection) as session:
        detail = activate_version(session, agent_id, 1)

    assert detail.agent.status is AgentStatus.TESTING


def test_activating_the_active_version_keeps_the_publication(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies a call that changes nothing does not unpublish the agent."""
    agent_id = _new_agent(connection)
    _publish_directly(connection, agent_id)

    with database_session(connection) as session:
        detail = activate_version(session, agent_id, 1)

    assert detail.agent.status is AgentStatus.PUBLISHED


def test_editing_a_system_agent_keeps_it_published(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies changing the model of the builder does not leave it out of the inventories."""
    with database_session(connection) as session:
        sync_system_agents(session)
        detail = add_version(session, EVAL_JUDGE_AGENT_ID, AgentSpecPatch(purpose="Otro"))

    assert detail.agent.status is AgentStatus.PUBLISHED


class _FailingEmbed:
    """Stands for an embedding call that fails; a class because nested functions are not allowed."""

    def __call__(self, *_args: object) -> None:
        """Raises the failure.

        Args:
            _args: The unused arguments of `embed`.

        Returns:
            None: never.

        Raises:
            ProviderError: Always.
        """
        raise ProviderError("Se cayó")


def _parse_vector(stored: str) -> list[float]:
    """Reads the text form in which pgvector returns a vector.

    Args:
        stored: The value of the column.

    Returns:
        list[float]: the components.
    """
    return [float(value) for value in stored.strip("[]").split(",")]


def test_create_agent_stores_the_justification_of_the_designer(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies the reasons stay with the version they explain, and later edits have none."""
    created = create_agent(connection, _draft(insert_model(connection)), "model: es barato")
    agent_id = created.agent.id

    with database_session(connection) as session:
        add_version(session, agent_id, AgentSpecPatch(purpose="Otro"))
        justifications = [v.designer_justification for v in list_versions(session, agent_id)]

    assert justifications == ["model: es barato", None]
