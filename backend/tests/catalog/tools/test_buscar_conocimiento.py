from decimal import Decimal
from unittest.mock import sentinel
from uuid import uuid4

import pytest

from bia.catalog.models.repository import EmbeddingModelUnavailableError
from bia.catalog.tools import buscar_conocimiento
from bia.catalog.tools.artifacts import ToolName
from bia.catalog.tools.base import ToolContext
from bia.catalog.tools.buscar_conocimiento import BuscarConocimientoTool
from bia.providers.artifacts import TokenUsage
from bia.providers.base import ProviderError
from bia.rag.artifacts import DEFAULT_TOP_K, KnowledgeSearchResult, RetrievedChunk
from bia.rag.repository import KnowledgeBaseNotFoundError
from bia.tracing.artifacts import StepType


def _search_result() -> KnowledgeSearchResult:
    """Builds a search with one fragment.

    Returns:
        KnowledgeSearchResult: the search.
    """
    chunk = RetrievedChunk(
        chunk_id=uuid4(),
        document="Tarifas",
        section="Hogar",
        content="Estrato 1: 412",
        similarity=0.9,
    )
    return KnowledgeSearchResult(
        chunks=[chunk],
        model_id=uuid4(),
        usage=TokenUsage(input_tokens=7, output_tokens=0),
        cost=Decimal("0.0001"),
        latency_ms=3,
    )


def test_run_searches_only_the_base_of_the_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies the base comes from the context, whatever the model asks for."""
    base_id = uuid4()
    calls = []
    search = _search_result()
    monkeypatch.setattr(
        buscar_conocimiento,
        "search_knowledge",
        lambda *args: calls.append(args) or search,
    )
    context = ToolContext(bind=sentinel.bind, knowledge_base_id=base_id)

    BuscarConocimientoTool().run({"consulta": "¿Cuánto vale el kWh?"}, context)

    assert calls == [(sentinel.bind, base_id, "¿Cuánto vale el kWh?", DEFAULT_TOP_K)]


def test_schema_does_not_let_the_model_name_a_base() -> None:
    """Verifies the only argument is the question, so an agent cannot leave its base."""
    schema = BuscarConocimientoTool().parameters_schema

    assert list(schema["properties"]) == ["consulta"]
    assert schema["additionalProperties"] is False
    assert BuscarConocimientoTool().name == ToolName.BUSCAR_CONOCIMIENTO


def test_result_is_a_retrieval_step_with_the_chunks_and_the_embedding_spend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies what the trace needs: the type, the sources, and the cost of the LLM call."""
    search = _search_result()
    monkeypatch.setattr(buscar_conocimiento, "search_knowledge", lambda *_args: search)
    context = ToolContext(bind=sentinel.bind, knowledge_base_id=uuid4())

    result = BuscarConocimientoTool().run({"consulta": "kWh"}, context)

    assert result.step_type is StepType.RETRIEVAL
    assert result.output["chunks"][0]["document"] == "Tarifas"
    assert result.output["chunks"][0]["section"] == "Hogar"
    assert result.output["chunks"][0]["chunk_id"] == str(search.chunks[0].chunk_id)
    assert (result.model_id, result.input_tokens) == (search.model_id, 7)
    assert result.cost == Decimal("0.0001")


def test_an_agent_without_a_base_gets_an_error_without_searching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies a spec stored without a base cannot end up reading some other one."""
    monkeypatch.setattr(buscar_conocimiento, "search_knowledge", _Raiser(AssertionError()))
    context = ToolContext(bind=sentinel.bind, knowledge_base_id=None)

    result = BuscarConocimientoTool().run({"consulta": "kWh"}, context)

    assert result.output is None
    assert "no tiene una base" in result.error
    assert result.step_type is StepType.RETRIEVAL


@pytest.mark.parametrize(
    "error",
    [
        ProviderError("api-key-interna"),
        EmbeddingModelUnavailableError("api-key-interna"),
        KnowledgeBaseNotFoundError("api-key-interna"),
    ],
)
def test_a_failed_search_reaches_the_model_without_internal_details(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    """Verifies the agent can say it could not check, and the failed retrieval stays on record."""
    monkeypatch.setattr(buscar_conocimiento, "search_knowledge", _Raiser(error))
    context = ToolContext(bind=sentinel.bind, knowledge_base_id=uuid4())

    result = BuscarConocimientoTool().run({"consulta": "kWh"}, context)

    assert "no está disponible" in result.error
    assert "api-key-interna" not in result.error
    assert result.step_type is StepType.RETRIEVAL


class _Raiser:
    """Stands for a search that fails; a class because nested functions are not allowed."""

    def __init__(self, error: Exception) -> None:
        """Keeps the error.

        Args:
            error (Exception): The error to raise when called.
        """
        self._error = error

    def __call__(self, *_args: object) -> KnowledgeSearchResult:
        """Raises the kept error.

        Args:
            _args: The unused arguments of the search.

        Returns:
            KnowledgeSearchResult: never.

        Raises:
            Exception: The kept error.
        """
        raise self._error
