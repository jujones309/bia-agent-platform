from uuid import uuid4

import pytest
from sqlalchemy import Connection, Uuid, column, func, select, table

from bia.providers.base import ProviderError
from bia.rag.chunking import InvalidDocumentError
from bia.rag.ingestion import ingest_document
from bia.rag.repository import KnowledgeBaseNotFoundError
from bia.rag.retrieval import search_knowledge
from tests.providers.fake import FakeModelProvider
from tests.rag.seed import FIRST_SECTION, build_draft, new_base

_CHUNKS = table("knowledge_chunks", column("document_id", Uuid))
_DOCUMENTS = table("knowledge_documents", column("id", Uuid))


def test_ingest_embeds_all_the_chunks_in_one_call_and_reports_the_cost(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies the batch, the catalog's model and a spend the caller can account for."""
    result = ingest_document(connection, new_base(connection), build_draft())

    assert provider.requested_models == ["text-embedding-3-small"]
    assert result.chunks_ingested == 2
    assert result.usage.input_tokens == 2  # the fake counts one token per text: a single batch
    assert result.cost > 0


def test_ingesting_a_title_again_replaces_the_document(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies idempotency: same document id, one row, and nothing left of the old text."""
    base_id = new_base(connection)
    documents_before = connection.execute(select(func.count()).select_from(_DOCUMENTS)).scalar_one()

    first = ingest_document(connection, base_id, build_draft())
    second = ingest_document(connection, base_id, build_draft("# C\nTexto de C"))

    assert second.document_id == first.document_id
    documents_after = connection.execute(select(func.count()).select_from(_DOCUMENTS)).scalar_one()
    assert documents_after == documents_before + 1
    chunks = search_knowledge(connection, base_id, "C\n\nTexto de C", top_k=5).chunks
    assert [chunk.section for chunk in chunks] == ["C"]


def test_ingesting_the_same_text_twice_does_not_duplicate_chunks(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies repeating an ingestion cannot inflate the results of a search."""
    base_id = new_base(connection)

    for _ in range(2):
        ingest_document(connection, base_id, build_draft())

    assert len(search_knowledge(connection, base_id, FIRST_SECTION, top_k=5).chunks) == 2


def test_the_same_title_can_exist_in_two_bases(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies re-ingesting into one base does not touch the document of another."""
    first = ingest_document(connection, new_base(connection), build_draft())
    second = ingest_document(connection, new_base(connection), build_draft())

    assert first.document_id != second.document_id


def test_a_failed_embedding_leaves_the_previous_version_intact(
    connection: Connection, monkeypatch: pytest.MonkeyPatch, provider: FakeModelProvider
) -> None:
    """Verifies a failed update does not leave an agent without its knowledge."""
    base_id = new_base(connection)
    ingest_document(connection, base_id, build_draft())
    monkeypatch.setattr(provider, "embed", _FailingEmbed())

    with pytest.raises(ProviderError):
        ingest_document(connection, base_id, build_draft("# C\nOtro texto"))

    assert _count_chunks(connection) == 2


def test_an_invalid_document_spends_nothing(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies the content is checked before the embedding."""
    with pytest.raises(InvalidDocumentError):
        ingest_document(connection, new_base(connection), build_draft("# Solo título"))

    assert provider.requested_models == []


def test_an_unknown_base_spends_nothing(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies the reference is checked before paying for an embedding."""
    missing_id = uuid4()

    with (
        pytest.raises(KnowledgeBaseNotFoundError, match=str(missing_id)),
        connection.begin_nested(),
    ):
        ingest_document(connection, missing_id, build_draft())

    assert provider.requested_models == []


def _count_chunks(connection: Connection) -> int:
    """Counts every fragment visible in the test's transaction.

    Args:
        connection: The connection of the test's transaction.

    Returns:
        int: the number of fragments.
    """
    return connection.execute(select(func.count()).select_from(_CHUNKS)).scalar_one()


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
