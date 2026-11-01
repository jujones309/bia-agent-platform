from collections.abc import Iterator
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import Connection, Engine, Uuid, column, table, update

from bia.agents.artifacts import AgentKind, AgentSpecPatch, AgentStatus
from bia.agents.registry import add_version
from bia.agents.repository import get_active_version, get_agent, list_versions
from bia.builder import system_agents
from bia.builder.system_agents import (
    CASE_GENERATOR_AGENT_ID,
    DESIGNER_AGENT_ID,
    DUPLICATE_JUDGE_AGENT_ID,
    EVAL_JUDGE_AGENT_ID,
    sync_system_agents,
)
from bia.catalog.models.artifacts import ModelSize
from bia.catalog.models.repository import (
    ModelSizeUnavailableError,
    get_catalog_model,
    list_catalog_models,
)
from bia.database.connection import database_session
from bia.database.migrate import apply_schema, apply_seeds
from bia.prompts.loader import PromptName, PromptVertical, load_prompt

_MODELS = table("models", column("size"), column("is_active"))
_AGENTS = table("agents", column("id", Uuid), column("name"), column("description_embedding"))


@pytest.fixture
def connection(integration_engine: Engine) -> Iterator[Connection]:
    """Provides a connection with the schema and the seeded catalog, rolled back at the end.

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
        yield open_connection
        transaction.rollback()


def _sync(connection: Connection) -> None:
    """Runs the sync the way a startup does.

    Args:
        connection: The connection of the test's transaction.

    Returns:
        None: the registry is updated.
    """
    with database_session(connection) as session:
        sync_system_agents(session)


def test_sync_registers_both_agents_as_published_parts_of_the_platform(
    connection: Connection,
) -> None:
    """Verifies the builder appears in the inventories, with the prompt of its file in the spec."""
    _sync(connection)

    with database_session(connection) as session:
        judge = get_agent(session, DUPLICATE_JUDGE_AGENT_ID)
        designer = get_agent(session, DESIGNER_AGENT_ID)
        judge_spec = get_active_version(session, DUPLICATE_JUDGE_AGENT_ID).spec
        designer_spec = get_active_version(session, DESIGNER_AGENT_ID).spec
        judge_model = get_catalog_model(session, judge_spec.model_id)
        designer_model = get_catalog_model(session, designer_spec.model_id)

    assert (judge.kind, judge.status) == (AgentKind.SYSTEM, AgentStatus.PUBLISHED)
    assert (designer.kind, designer.status) == (AgentKind.SYSTEM, AgentStatus.PUBLISHED)
    assert judge_spec.system_prompt == load_prompt(
        PromptVertical.BUILDER_DUPLICATES, PromptName.JUDGE
    )
    assert designer_spec.system_prompt == load_prompt(
        PromptVertical.BUILDER_DESIGNER, PromptName.DESIGNER
    )
    assert judge_model.size is ModelSize.SMALL
    assert designer_model.size is ModelSize.LARGE


def test_sync_registers_the_agents_of_the_evals_with_their_prompts(connection: Connection) -> None:
    """Verifies the generator and the judge of the evals exist, and each runs its own prompt."""
    _sync(connection)

    with database_session(connection) as session:
        generator_spec = get_active_version(session, CASE_GENERATOR_AGENT_ID).spec
        judge_spec = get_active_version(session, EVAL_JUDGE_AGENT_ID).spec
        generator_model = get_catalog_model(session, generator_spec.model_id)
        judge_model = get_catalog_model(session, judge_spec.model_id)

    assert generator_spec.system_prompt == load_prompt(
        PromptVertical.EVALS, PromptName.CASE_GENERATOR
    )
    assert judge_spec.system_prompt == load_prompt(PromptVertical.EVALS, PromptName.JUDGE)
    assert generator_model.size is ModelSize.LARGE
    assert judge_model.size is ModelSize.SMALL


def test_sync_is_idempotent(connection: Connection) -> None:
    """Verifies each startup does not add versions when nothing changed."""
    _sync(connection)
    with database_session(connection) as session:
        versions_before = list_versions(session, DUPLICATE_JUDGE_AGENT_ID)

    _sync(connection)

    with database_session(connection) as session:
        assert list_versions(session, DUPLICATE_JUDGE_AGENT_ID) == versions_before


def test_changing_the_prompt_file_adds_a_version_and_keeps_the_chosen_model(
    connection: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies prompts are versioned, and that a startup does not undo an operator's model."""
    _sync(connection)
    with database_session(connection) as session:
        small_model = get_active_version(session, DUPLICATE_JUDGE_AGENT_ID).spec.model_id
        other_model = next(
            model.id
            for model in list_catalog_models(session, only_active=True)
            if model.size is ModelSize.LARGE
        )
        patched = add_version(
            session, DUPLICATE_JUDGE_AGENT_ID, AgentSpecPatch(model_id=other_model)
        )
    assert small_model != other_model
    monkeypatch.setattr(system_agents, "load_prompt", lambda _vertical, _name: "Prompt nuevo")

    _sync(connection)

    with database_session(connection) as session:
        active = get_active_version(session, DUPLICATE_JUDGE_AGENT_ID)
    assert active.version_number == patched.active_version.version_number + 1
    assert active.spec.system_prompt == "Prompt nuevo"
    assert active.spec.model_id == other_model


def test_sync_restores_a_renamed_agent(connection: Connection) -> None:
    """Verifies the code owns the identity of a system agent."""
    _sync(connection)
    connection.execute(update(_AGENTS).where(_AGENTS.c.id == DESIGNER_AGENT_ID).values(name="Otro"))

    _sync(connection)

    with database_session(connection) as session:
        assert get_agent(session, DESIGNER_AGENT_ID).name == "Diseñador de agentes"


def test_sync_fails_clearly_if_the_catalog_lacks_a_size(
    connection: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies an incomplete catalog stops the startup instead of leaving the builder broken."""
    new_agent = replace(system_agents._DEFINITIONS[0], agent_id=uuid4())
    monkeypatch.setattr(system_agents, "_DEFINITIONS", (new_agent,))
    connection.execute(
        update(_MODELS).where(_MODELS.c.size == ModelSize.SMALL).values(is_active=False)
    )

    with pytest.raises(ModelSizeUnavailableError, match="'small'"):
        _sync(connection)
