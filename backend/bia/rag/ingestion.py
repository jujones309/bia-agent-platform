import logging
from uuid import UUID

from sqlalchemy import Connection, Engine

from bia.catalog.models.repository import find_embedding_model
from bia.database.connection import database_session
from bia.providers.cost import compute_cost
from bia.providers.factory import get_provider
from bia.rag.artifacts import DocumentDraft, IngestionResult
from bia.rag.chunking import chunk_document
from bia.rag.repository import get_knowledge_base, replace_document_chunks, upsert_document

logger = logging.getLogger(__name__)


def ingest_document(
    bind: Engine | Connection, knowledge_base_id: UUID, draft: DocumentDraft
) -> IngestionResult:
    """Divides a document, embeds its chunks in one batch and stores them.

    Exists as the single way knowledge enters a base; used by the knowledge API. Ingesting a
    title again replaces that document. The embedding happens between two short transactions,
    so no connection stays open during the LLM call, and a failure leaves the previous version
    of the document intact.

    Args:
        bind: The database handle to read and write through.
        knowledge_base_id: The base that receives the document.
        draft: The document with its text.

    Returns:
        IngestionResult: the stored document, with what its embeddings cost.

    Raises:
        InvalidDocumentError: If the document cannot be divided into chunks.
        KnowledgeBaseNotFoundError: If the base does not exist.
        EmbeddingModelUnavailableError: If the catalog has no active embedding model.
        ProviderError: If the embedding call fails.
    """
    chunks = chunk_document(draft)
    with database_session(bind) as session:
        get_knowledge_base(session, knowledge_base_id)
        model = find_embedding_model(session)
    logger.info("Embedding %d chunks of document '%s'", len(chunks), draft.title)
    texts = [chunk.content for chunk in chunks]
    result = get_provider(model.provider).embed(texts, model.provider_model_id)
    with database_session(bind) as session:
        document_id = upsert_document(session, knowledge_base_id, draft)
        replace_document_chunks(session, document_id, chunks, result.embeddings)
    cost = compute_cost(result.usage, model)
    logger.info(
        "Document %s ingested with %d chunks in %d ms, cost $%s",
        document_id,
        len(chunks),
        result.latency_ms,
        cost,
    )
    return IngestionResult(
        document_id=document_id,
        chunks_ingested=len(chunks),
        model_id=model.id,
        usage=result.usage,
        cost=cost,
        latency_ms=result.latency_ms,
    )
