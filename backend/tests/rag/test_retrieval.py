from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import Connection, column, func, select, table, text, update

from bia.catalog.models.repository import EmbeddingModelUnavailableError
from bia.database.connection import database_session
from bia.rag import retrieval
from bia.rag.config import RAG_CONFIG, RagConfig
from bia.rag.ingestion import ingest_document
from bia.rag.repository import KnowledgeBaseNotFoundError, search_chunks
from bia.rag.retrieval import search_knowledge
from tests.providers.fake import FakeModelProvider
from tests.rag.seed import FIRST_SECTION, SECOND_SECTION, build_draft, new_base

_MODELS = table("models", column("size"), column("is_active"))
_MANY_SECTIONS = 60  # more than the candidates the vector index considers in its first pass


def test_ingest_and_search_finds_the_closest_chunk_with_its_source(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies the cosine order on real SQL, since the fake gives equal texts equal vectors."""
    base_id = new_base(connection)
    ingest_document(connection, base_id, build_draft())

    result = search_knowledge(connection, base_id, SECOND_SECTION, top_k=5)

    assert [chunk.section for chunk in result.chunks] == ["B", "A"]
    closest = result.chunks[0]
    assert (closest.document, closest.content) == ("Tarifas", SECOND_SECTION)
    assert closest.similarity == pytest.approx(1)
    assert result.chunks[1].similarity < closest.similarity


def test_top_k_limits_the_search(connection: Connection, provider: FakeModelProvider) -> None:
    """Verifies the limit reaches the query."""
    base_id = new_base(connection)
    ingest_document(connection, base_id, build_draft())

    assert len(search_knowledge(connection, base_id, FIRST_SECTION, top_k=1).chunks) == 1


def test_search_never_returns_chunks_of_another_base(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies the isolation that keeps an agent inside the base it was assigned."""
    own_base = new_base(connection)
    other_base = new_base(connection)
    ingest_document(connection, other_base, build_draft())

    assert search_knowledge(connection, own_base, FIRST_SECTION, top_k=5).chunks == []


def test_chunks_below_the_minimum_similarity_are_left_out_in_order(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies the cut happens on real SQL, keeping only what is close enough."""
    base_id = new_base(connection)
    ingest_document(connection, base_id, build_draft())
    query = provider.embed([SECOND_SECTION], "any").embeddings[0]

    with database_session(connection) as session:
        scanned = RAG_CONFIG.exact_search_maximum_chunks
        everything = search_chunks(session, base_id, query, 5, -1, scanned)
        between = (everything[0].similarity + everything[1].similarity) / 2
        closest = search_chunks(session, base_id, query, 5, between, scanned)

    assert [chunk.section for chunk in everything] == ["B", "A"]
    assert [chunk.section for chunk in closest] == ["B"]


def test_an_off_topic_search_returns_no_chunks_and_still_accounts_for_the_embedding(
    connection: Connection, provider: FakeModelProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the configured minimum reaches the search, and the cost of asking is not lost."""
    monkeypatch.setattr(retrieval, "RAG_CONFIG", RagConfig(minimum_similarity=1))
    base_id = new_base(connection)
    ingest_document(connection, base_id, build_draft())

    result = search_knowledge(connection, base_id, "¿Cuál es la capital de Francia?", top_k=5)

    assert result.chunks == []
    assert result.cost > 0


def test_the_index_finds_a_base_hidden_behind_another(
    connection: Connection, provider: FakeModelProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the iterative scan: the first candidates of the index are of the other base."""
    monkeypatch.setattr(retrieval, "RAG_CONFIG", RagConfig(exact_search_maximum_chunks=0))
    large_base = new_base(connection)
    small_base = new_base(connection)
    sections = "\n".join(f"# S{i}\nTexto {i}" for i in range(_MANY_SECTIONS))
    ingest_document(connection, large_base, build_draft(content=sections))
    ingest_document(connection, small_base, build_draft())
    connection.execute(text("SET LOCAL enable_seqscan = off"))
    connection.execute(text("SET LOCAL enable_sort = off"))

    chunks = search_knowledge(connection, small_base, "S1\n\nTexto 1", top_k=2).chunks

    assert {chunk.section for chunk in chunks} == {"A", "B"}


@pytest.mark.parametrize(
    ("exact_search_maximum_chunks", "index_allowed"),
    [(2, "off"), (1, "on")],  # the base has exactly two chunks: the limit is inclusive
)
def test_only_a_base_above_the_limit_uses_the_index(
    connection: Connection,
    provider: FakeModelProvider,
    monkeypatch: pytest.MonkeyPatch,
    exact_search_maximum_chunks: int,
    index_allowed: str,
) -> None:
    """Verifies the route, because the index would silently lose fragments of a small base."""
    config = RagConfig(exact_search_maximum_chunks=exact_search_maximum_chunks)
    monkeypatch.setattr(retrieval, "RAG_CONFIG", config)
    base_id = new_base(connection)
    ingest_document(connection, base_id, build_draft())

    search_knowledge(connection, base_id, FIRST_SECTION, top_k=5)

    assert connection.execute(text("SHOW enable_indexscan")).scalar_one() == index_allowed


@pytest.mark.parametrize(
    ("valid_from_days", "valid_until_days", "retrieved"),
    [
        (None, -1, False),  # expired yesterday
        (1, None, False),  # takes effect tomorrow
        (None, 0, True),  # the last day still counts
        (0, None, True),  # the first day already counts
        (-1, 1, True),
    ],
)
def test_search_only_considers_documents_in_force(
    connection: Connection,
    provider: FakeModelProvider,
    valid_from_days: int | None,
    valid_until_days: int | None,
    retrieved: bool,
) -> None:
    """Verifies an expired tariff is never given to a customer, with inclusive limits."""
    base_id = new_base(connection)
    today = connection.execute(select(func.current_date())).scalar_one()
    ingest_document(
        connection,
        base_id,
        build_draft(
            valid_from=None if valid_from_days is None else today + timedelta(valid_from_days),
            valid_until=None if valid_until_days is None else today + timedelta(valid_until_days),
        ),
    )

    chunks = search_knowledge(connection, base_id, FIRST_SECTION, top_k=5).chunks

    assert bool(chunks) is retrieved


def test_search_fails_clearly_without_an_embedding_model(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies a misconfigured catalog is named instead of failing inside the provider."""
    base_id = new_base(connection)
    connection.execute(update(_MODELS).where(_MODELS.c.size == "embedding").values(is_active=False))

    with pytest.raises(EmbeddingModelUnavailableError), connection.begin_nested():
        search_knowledge(connection, base_id, "pregunta", top_k=5)


def test_an_unknown_base_spends_nothing(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies the reference is checked before paying for an embedding."""
    missing_id = uuid4()

    with (
        pytest.raises(KnowledgeBaseNotFoundError, match=str(missing_id)),
        connection.begin_nested(),
    ):
        search_knowledge(connection, missing_id, "pregunta", top_k=5)

    assert provider.requested_models == []
