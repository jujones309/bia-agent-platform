from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from bia.api.dependencies import get_database_engine, get_session
from bia.catalog.models.repository import EmbeddingModelUnavailableError
from bia.providers.base import ProviderError
from bia.rag.artifacts import (
    DEFAULT_TOP_K,
    MAX_TOP_K,
    DocumentDraft,
    IngestionResult,
    KnowledgeBase,
    KnowledgeBaseDraft,
    KnowledgeSearchResult,
)
from bia.rag.chunking import InvalidDocumentError
from bia.rag.ingestion import ingest_document
from bia.rag.repository import KnowledgeBaseNotFoundError, insert_knowledge_base
from bia.rag.retrieval import search_knowledge

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge"])


@router.post("", response_model=KnowledgeBase, status_code=status.HTTP_201_CREATED)
def post_knowledge_base(
    draft: KnowledgeBaseDraft, session: Annotated[Session, Depends(get_session)]
) -> KnowledgeBase:
    """Creates a knowledge base.

    Exists so a spec has a base to reference; served as `POST /knowledge-bases`.

    Args:
        draft: The name and description of the base.
        session: The session of the request.

    Returns:
        KnowledgeBase: the new base.
    """
    return insert_knowledge_base(session, draft)


@router.post("/{knowledge_base_id}/ingest", response_model=IngestionResult)
def post_ingest(
    knowledge_base_id: UUID,
    draft: DocumentDraft,
    engine: Annotated[Engine, Depends(get_database_engine)],
) -> IngestionResult:
    """Ingests one document, replacing the one with the same title if it exists.

    Exists to load and update knowledge; served as `POST /knowledge-bases/{id}/ingest`. Uses the
    engine because a request-scoped session would stay open during the embedding call.

    Args:
        knowledge_base_id: The base that receives the document.
        draft: The document with its text.
        engine: The engine to read and write through.

    Returns:
        IngestionResult: the stored document, with what its embeddings cost.

    Raises:
        HTTPException: A 404 if the base does not exist, a 422 if the document cannot be divided,
            a 502 if the embedding call fails, or a 503 if the catalog has no embedding model.
    """
    try:
        return ingest_document(engine, knowledge_base_id, draft)
    except KnowledgeBaseNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except InvalidDocumentError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    except ProviderError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error
    except EmbeddingModelUnavailableError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error


@router.get("/{knowledge_base_id}/search", response_model=KnowledgeSearchResult)
def get_search(
    knowledge_base_id: UUID,
    engine: Annotated[Engine, Depends(get_database_engine)],
    q: Annotated[str, Query(min_length=1)],
    top_k: Annotated[int, Query(ge=1, le=MAX_TOP_K)] = DEFAULT_TOP_K,
) -> KnowledgeSearchResult:
    """Searches a knowledge base directly, without an agent.

    Exists so a person can check what an agent would retrieve; served as
    `GET /knowledge-bases/{id}/search`. Uses the engine because a request-scoped session would
    stay open during the embedding call.

    Args:
        knowledge_base_id: The base to search in.
        engine: The engine to read through.
        q: The question, in natural language.
        top_k: The maximum number of fragments.

    Returns:
        KnowledgeSearchResult: the fragments, closest first, with what the embedding cost.

    Raises:
        HTTPException: A 404 if the base does not exist, a 502 if the embedding call fails, or a
            503 if the catalog has no embedding model.
    """
    try:
        return search_knowledge(engine, knowledge_base_id, q, top_k)
    except KnowledgeBaseNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except ProviderError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error
    except EmbeddingModelUnavailableError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error
