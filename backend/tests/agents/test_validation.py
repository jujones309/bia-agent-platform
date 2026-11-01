from datetime import UTC, datetime
from uuid import uuid4

import pytest

from bia.agents.artifacts import AgentSpec, AgentSpecPatch
from bia.agents.validation import (
    InvalidAgentSpecError,
    find_model_problems,
    find_tool_problems,
    merge_spec_patch,
)
from bia.catalog.models.artifacts import CatalogModel, ModelSize
from bia.catalog.tools.artifacts import CatalogTool, RiskLevel


def _model(size: ModelSize = ModelSize.SMALL, is_active: bool = True) -> CatalogModel:
    """Builds a catalog model.

    Args:
        size: The category of the model.
        is_active: Whether new specs can choose it.

    Returns:
        CatalogModel: the entry.
    """
    return CatalogModel(
        id=uuid4(),
        name="Modelo",
        provider="openai",
        provider_model_id="modelo",
        size=size,
        input_cost_per_million=1,
        output_cost_per_million=1,
        context_window=1000,
        recommended_use="Pruebas",
        is_active=is_active,
        created_at=datetime.now(UTC),
    )


def _tool(name: str, is_active: bool = True) -> CatalogTool:
    """Builds a catalog tool.

    Args:
        name: The name of the tool.
        is_active: Whether agents can use it.

    Returns:
        CatalogTool: the entry.
    """
    return CatalogTool(
        id=uuid4(),
        name=name,
        description="Herramienta",
        parameters_schema={},
        risk_level=RiskLevel.LOW,
        is_active=is_active,
        created_at=datetime.now(UTC),
    )


def _spec(**changes: object) -> AgentSpec:
    """Builds a valid spec.

    Args:
        changes: The values that differ from the defaults.

    Returns:
        AgentSpec: the spec.
    """
    values = {"purpose": "Atender", "system_prompt": "Eres útil", "model_id": uuid4()}
    return AgentSpec.model_validate({**values, **changes})


def test_an_active_chat_model_can_be_assigned() -> None:
    """Verifies the catalog's normal entries pass, so the checks below are meaningful."""
    model = _model()

    assert find_model_problems(model.id, [_model(), model]) == []


def test_a_model_outside_the_catalog_is_named() -> None:
    """Verifies an invented identifier is a hard error that says which one it was."""
    unknown_id = uuid4()

    assert str(unknown_id) in find_model_problems(unknown_id, [_model()])[0]


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        (_model(is_active=False), "retired"),
        (_model(size=ModelSize.EMBEDDING), "only generates embeddings"),
    ],
)
def test_catalog_models_that_cannot_serve_a_new_spec_are_rejected(
    model: CatalogModel, expected: str
) -> None:
    """Verifies retired models stay closed, and an embedding model never reaches a chat call."""
    assert expected in find_model_problems(model.id, [model])[0]


def test_every_unavailable_tool_is_reported_and_available_ones_are_not() -> None:
    """Verifies one attempt is enough to learn all the tools to fix."""
    tools = [_tool("activa"), _tool("retirada", is_active=False)]

    problems = find_tool_problems(["activa", "retirada", "inventada"], tools)

    assert problems == [
        "The tool 'retirada' is retired",
        "The tool catalog has no tool named 'inventada'",
    ]


def test_merge_changes_only_the_fields_sent() -> None:
    """Verifies a small adjustment keeps the rest of the spec intact."""
    spec = _spec(guardrails=["No inventes"], tool_names=["consultar_factura"])

    merged = merge_spec_patch(spec, AgentSpecPatch(system_prompt="Sé breve"))

    assert merged == spec.model_copy(update={"system_prompt": "Sé breve"})


def test_merge_can_detach_the_knowledge_base_with_an_explicit_null() -> None:
    """Verifies null is told apart from a field that was left out."""
    spec = _spec(knowledge_base_id=uuid4())

    untouched = merge_spec_patch(spec, AgentSpecPatch(purpose="Otro"))
    detached = merge_spec_patch(spec, AgentSpecPatch(knowledge_base_id=None))

    assert untouched.knowledge_base_id == spec.knowledge_base_id
    assert detached.knowledge_base_id is None


@pytest.mark.parametrize(
    ("patch", "field"),
    [
        (AgentSpecPatch(system_prompt=None), "system_prompt"),
        (AgentSpecPatch(purpose=""), "purpose"),
        (AgentSpecPatch(tool_names=None), "tool_names"),
        (AgentSpecPatch(max_iterations=21), "max_iterations"),
    ],
)
def test_merge_rejects_results_that_break_the_rules_of_a_spec(
    patch: AgentSpecPatch, field: str
) -> None:
    """Verifies the patch cannot bypass the constraints that `AgentSpec` declares."""
    with pytest.raises(InvalidAgentSpecError, match=field):
        merge_spec_patch(_spec(), patch)


@pytest.mark.parametrize("sent", [{}, {"purpose": "Atender"}])
def test_merge_rejects_a_change_that_changes_nothing(sent: dict[str, str]) -> None:
    """Verifies the history does not fill up with identical versions."""
    with pytest.raises(InvalidAgentSpecError, match="identical"):
        merge_spec_patch(_spec(), AgentSpecPatch.model_validate(sent))


def test_patch_offers_exactly_the_fields_of_a_spec() -> None:
    """Verifies a field added to the spec cannot be forgotten in the patch."""
    assert set(AgentSpecPatch.model_fields) == set(AgentSpec.model_fields)
