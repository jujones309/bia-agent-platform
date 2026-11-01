import logging
from uuid import UUID

from sqlalchemy import Connection, Engine

from bia.catalog.models.repository import find_embedding_model
from bia.database.connection import database_session
from bia.providers.cost import compute_cost
from bia.providers.factory import get_provider
from bia.rag.artifacts import KnowledgeSearchResult
from bia.rag.config import RAG_CONFIG
from bia.rag.repository import get_knowledge_base, search_chunks

logger = logging.getLogger(__name__)


def search_knowledge(
    bind: Engine | Connection, knowledge_base_id: UUID, query: str, top_k: int
) -> KnowledgeSearchResult:
    """Finds the fragments of a base that best answer a question.

    Exists as the single way to retrieve knowledge; used by `buscar_conocimiento` and by the
    knowledge API. Each read is a short transaction, so no connection stays open during the
    LLM call, and an unknown base fails before the embedding is paid for.

    Args:
        bind: The database handle to read through.
        knowledge_base_id: The only base to search in.
        query: The question, in natural language.
        top_k: The maximum number of fragments.

    Returns:
        KnowledgeSearchResult: the fragments similar enough to the question, closest first, with
            what the embedding cost; no fragments if the question is off topic.

    Raises:
        KnowledgeBaseNotFoundError: If the base does not exist.
        EmbeddingModelUnavailableError: If the catalog has no active embedding model.
        ProviderError: If the embedding call fails.
    """
    with database_session(bind) as session:
        get_knowledge_base(session, knowledge_base_id)
        model = find_embedding_model(session)
    embedding = get_provider(model.provider).embed([query], model.provider_model_id)
    with database_session(bind) as session:
        chunks = search_chunks(
            session,
            knowledge_base_id,
            embedding.embeddings[0],
            top_k,
            RAG_CONFIG.minimum_similarity,
            RAG_CONFIG.exact_search_maximum_chunks,
        )
    logger.info("Search in knowledge base %s found %d chunks", knowledge_base_id, len(chunks))
    return KnowledgeSearchResult(
        chunks=chunks,
        model_id=model.id,
        usage=embedding.usage,
        cost=compute_cost(embedding.usage, model),
        latency_ms=embedding.latency_ms,
    )
