from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from bia.api import rag as rag_router
from bia.api.dependencies import get_database_engine, get_session
from bia.api.main import app
from bia.catalog.models.repository import EmbeddingModelUnavailableError
from bia.providers.artifacts import TokenUsage
from bia.providers.base import ProviderError
from bia.rag.artifacts import (
    IngestionResult,
    KnowledgeBase,
    KnowledgeSearchResult,
    RetrievedChunk,
)
from bia.rag.chunking import InvalidDocumentError
from bia.rag.repository import KnowledgeBaseNotFoundError

_DOCUMENT_BODY = {"title": "Tarifas", "document_type": "tariff", "content": "# A\nTexto"}
_USAGE = TokenUsage(input_tokens=4, output_tokens=0)


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
    """Stands for a function that fails; a class because nested functions are not allowed."""

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


def _search_result() -> KnowledgeSearchResult:
    """Builds a search with one fragment.

    Returns:
        KnowledgeSearchResult: the search.
    """
    chunk = RetrievedChunk(
        chunk_id=uuid4(), document="Tarifas", section="A", content="Texto", similarity=0.8
    )
    return KnowledgeSearchResult(
        chunks=[chunk], model_id=uuid4(), usage=_USAGE, cost=Decimal("0.01"), latency_ms=2
    )


def test_create_answers_201_with_the_id_a_spec_can_reference(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the body reaches the repository and the identifier comes back."""
    base = KnowledgeBase(
        id=uuid4(), name="Facturación", description="Tarifas", created_at=datetime.now(UTC)
    )
    drafts = []
    monkeypatch.setattr(
        rag_router, "insert_knowledge_base", lambda _session, draft: drafts.append(draft) or base
    )

    response = client.post(
        "/knowledge-bases", json={"name": "Facturación", "description": "Tarifas"}
    )

    assert response.status_code == 201
    assert response.json()["id"] == str(base.id)
    assert drafts[0].name == "Facturación"


def test_create_rejects_an_empty_name(client: TestClient) -> None:
    """Verifies a base cannot be created without something to recognize it by."""
    response = client.post("/knowledge-bases", json={"name": "", "description": "Tarifas"})

    assert response.status_code == 422


def test_ingest_passes_the_document_to_the_base_of_the_path(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the target base and that the response accounts for the spending."""
    base_id = uuid4()
    calls = []
    result = IngestionResult(
        document_id=uuid4(),
        chunks_ingested=3,
        model_id=uuid4(),
        usage=_USAGE,
        cost=Decimal("0.02"),
        latency_ms=5,
    )
    monkeypatch.setattr(
        rag_router, "ingest_document", lambda _engine, *args: calls.append(args) or result
    )

    response = client.post(f"/knowledge-bases/{base_id}/ingest", json=_DOCUMENT_BODY)

    assert response.status_code == 200
    assert response.json()["chunks_ingested"] == 3
    assert response.json()["usage"]["input_tokens"] == 4
    assert calls[0][0] == base_id
    assert calls[0][1].title == "Tarifas"


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (KnowledgeBaseNotFoundError("no existe"), 404),
        (InvalidDocumentError("sin texto"), 422),
        (ProviderError("se cayó"), 502),
        (EmbeddingModelUnavailableError("sin modelo"), 503),
    ],
)
def test_ingest_explains_why_it_could_not_store_the_document(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, error: Exception, expected_status: int
) -> None:
    """Verifies each failure is the caller's or an upstream one, and never an opaque 500."""
    monkeypatch.setattr(rag_router, "ingest_document", _Raiser(error))

    response = client.post(f"/knowledge-bases/{uuid4()}/ingest", json=_DOCUMENT_BODY)

    assert response.status_code == expected_status
    assert response.json()["detail"] == str(error)


def test_ingest_rejects_an_unknown_document_type(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies a type without a chunking strategy does not reach the ingestion."""
    monkeypatch.setattr(rag_router, "ingest_document", _Raiser(AssertionError("must not run")))
    body = {**_DOCUMENT_BODY, "document_type": "contract"}

    assert client.post(f"/knowledge-bases/{uuid4()}/ingest", json=body).status_code == 422


def test_search_returns_the_chunks_with_their_source(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the query and the limit reach the search and the sources reach the caller."""
    base_id = uuid4()
    calls = []
    result = _search_result()
    monkeypatch.setattr(
        rag_router, "search_knowledge", lambda _engine, *args: calls.append(args) or result
    )

    response = client.get(f"/knowledge-bases/{base_id}/search", params={"q": "kWh", "top_k": 2})

    assert response.status_code == 200
    assert response.json()["chunks"][0]["document"] == "Tarifas"
    assert response.json()["chunks"][0]["section"] == "A"
    assert calls == [(base_id, "kWh", 2)]


@pytest.mark.parametrize(
    "params", [{}, {"q": ""}, {"q": "kWh", "top_k": 0}, {"q": "k", "top_k": 21}]
)
def test_search_rejects_invalid_parameters(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, params: dict[str, object]
) -> None:
    """Verifies an empty query or an unbounded limit never reaches the embedding."""
    monkeypatch.setattr(rag_router, "search_knowledge", _Raiser(AssertionError("must not run")))

    assert client.get(f"/knowledge-bases/{uuid4()}/search", params=params).status_code == 422


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (KnowledgeBaseNotFoundError("no existe"), 404),
        (ProviderError("se cayó"), 502),
        (EmbeddingModelUnavailableError("sin modelo"), 503),
    ],
)
def test_search_explains_why_it_could_not_run(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, error: Exception, expected_status: int
) -> None:
    """Verifies each failure of a search reaches the caller with its reason."""
    monkeypatch.setattr(rag_router, "search_knowledge", _Raiser(error))

    response = client.get(f"/knowledge-bases/{uuid4()}/search", params={"q": "kWh"})

    assert response.status_code == expected_status
    assert response.json()["detail"] == str(error)


def test_knowledge_endpoints_require_credentials() -> None:
    """Verifies the knowledge stays behind the shared password."""
    assert TestClient(app).get(f"/knowledge-bases/{uuid4()}/search?q=kWh").status_code == 401
