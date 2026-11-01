import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from bia.database.queries import DatabaseTable, SqlOperation, load_sql
from bia.rag.artifacts import (
    DocumentChunk,
    DocumentDraft,
    KnowledgeBase,
    KnowledgeBaseDraft,
    KnowledgeDocument,
    RetrievedChunk,
)


class KnowledgeBaseNotFoundError(LookupError):
    """Signals that there is no knowledge base with the requested identifier.

    Exists so a wrong reference fails before an embedding is paid for. Raised by
    `get_knowledge_base` and translated to a 404 by `bia/api/rag.py`.
    """


class KnowledgeDocumentNotFoundError(LookupError):
    """Signals that a base has no current document with the requested identifier.

    Exists so retiring a wrong or already retired document fails clearly. Raised by
    `retire_document` and translated to a 404 by `bia/api/rag.py`.
    """


def insert_knowledge_base(session: Session, draft: KnowledgeBaseDraft) -> KnowledgeBase:
    """Creates a knowledge base.

    Exists as the single write of new bases; used by the knowledge API.

    Args:
        session: The open session whose transaction contains the write.
        draft: The name and description of the base.

    Returns:
        KnowledgeBase: the stored base.
    """
    sql = load_sql(DatabaseTable.KNOWLEDGE_BASES, SqlOperation.INSERT)
    row = session.execute(text(sql), draft.model_dump()).mappings().one()
    return KnowledgeBase.model_validate(dict(row))


def list_knowledge_bases(session: Session) -> list[KnowledgeBase]:
    """Lists the knowledge bases, ordered by name.

    Exists so the designer and the people reviewing a spec can only assign a base that exists; used
    by `bia/builder/designer/` and by the knowledge API.

    Args:
        session: The open session to read through.

    Returns:
        list[KnowledgeBase]: every base.
    """
    sql = load_sql(DatabaseTable.KNOWLEDGE_BASES, SqlOperation.LIST)
    rows = session.execute(text(sql)).mappings()
    return [KnowledgeBase.model_validate(dict(row)) for row in rows]


def get_knowledge_base(session: Session, knowledge_base_id: UUID) -> KnowledgeBase:
    """Retrieves one knowledge base.

    Exists to check a reference before using it; used by the ingestion, the search and the
    validation of agent specs.

    Args:
        session: The open session to read through.
        knowledge_base_id: The base to look up.

    Returns:
        KnowledgeBase: the base.

    Raises:
        KnowledgeBaseNotFoundError: If no base has that identifier.
    """
    sql = load_sql(DatabaseTable.KNOWLEDGE_BASES, SqlOperation.GET_BY_ID)
    parameters = {"knowledge_base_id": str(knowledge_base_id)}
    row = session.execute(text(sql), parameters).mappings().one_or_none()
    if row is None:
        raise KnowledgeBaseNotFoundError(f"There is no knowledge base with id {knowledge_base_id}")
    return KnowledgeBase.model_validate(dict(row))


def list_documents(session: Session, knowledge_base_id: UUID) -> list[KnowledgeDocument]:
    """Lists the current documents of a base, ordered by title.

    Exists so a person can see what a base holds before using it; used by the knowledge API.

    Args:
        session: The open session to read through.
        knowledge_base_id: The base to look up.

    Returns:
        list[KnowledgeDocument]: its documents; empty if it has none.
    """
    sql = load_sql(DatabaseTable.KNOWLEDGE_DOCUMENTS, SqlOperation.LIST_BY_BASE)
    rows = session.execute(text(sql), {"knowledge_base_id": str(knowledge_base_id)}).mappings()
    return [KnowledgeDocument.model_validate(dict(row)) for row in rows]


def retire_document(session: Session, knowledge_base_id: UUID, document_id: UUID) -> None:
    """Takes a document out of its base and removes its fragments, so nothing can retrieve it.

    Exists because the row is the record that the document existed, while the fragments are derived
    data: the traces keep their own copy of what each search returned. Used by the knowledge API.
    Ingesting the same title again puts the document back in force.

    Args:
        session: The open session whose transaction contains the writes.
        knowledge_base_id: The base the document must belong to.
        document_id: The document to retire.

    Returns:
        None: the document is retired inside the session's transaction.

    Raises:
        KnowledgeDocumentNotFoundError: If the base has no current document with that identifier.
    """
    parameters = {"knowledge_base_id": str(knowledge_base_id), "document_id": str(document_id)}
    sql = load_sql(DatabaseTable.KNOWLEDGE_DOCUMENTS, SqlOperation.RETIRE)
    if session.execute(text(sql), parameters).one_or_none() is None:
        raise KnowledgeDocumentNotFoundError(
            f"Knowledge base {knowledge_base_id} has no current document {document_id}"
        )
    delete_sql = load_sql(DatabaseTable.KNOWLEDGE_CHUNKS, SqlOperation.DELETE_BY_DOCUMENT)
    session.execute(text(delete_sql), {"document_id": str(document_id)})


def upsert_document(session: Session, knowledge_base_id: UUID, draft: DocumentDraft) -> UUID:
    """Creates a document or refreshes the one with the same title, locking its row.

    Exists so ingestion is idempotent per document, and so concurrent ingestions of one
    document happen one after the other; used by `ingest_document`.

    Args:
        session: The open session whose transaction contains the write.
        knowledge_base_id: The base the document belongs to.
        draft: The document being ingested.

    Returns:
        UUID: the identifier of the document, stable across ingestions.
    """
    parameters = {
        "knowledge_base_id": str(knowledge_base_id),
        "title": draft.title,
        "document_type": draft.document_type,
        "valid_from": draft.valid_from,
        "valid_until": draft.valid_until,
    }
    sql = load_sql(DatabaseTable.KNOWLEDGE_DOCUMENTS, SqlOperation.UPSERT)
    return session.execute(text(sql), parameters).scalar_one()


def replace_document_chunks(
    session: Session,
    document_id: UUID,
    chunks: list[DocumentChunk],
    embeddings: list[list[float]],
) -> None:
    """Replaces all the chunks of a document.

    Exists so a new version of a document leaves nothing of the previous one; used by
    `ingest_document`.

    Args:
        session: The open session whose transaction contains the writes.
        document_id: The document the chunks belong to.
        chunks: The new chunks.
        embeddings: The vector of each chunk, in the same order.

    Returns:
        None: the rows are written inside the session's transaction.
    """
    delete_sql = load_sql(DatabaseTable.KNOWLEDGE_CHUNKS, SqlOperation.DELETE_BY_DOCUMENT)
    session.execute(text(delete_sql), {"document_id": str(document_id)})
    rows = [
        {
            "document_id": str(document_id),
            "content": chunk.content,
            "metadata": chunk.metadata.model_dump_json(),
            "embedding": json.dumps(embedding),
        }
        for chunk, embedding in zip(chunks, embeddings, strict=True)
    ]
    session.execute(text(load_sql(DatabaseTable.KNOWLEDGE_CHUNKS, SqlOperation.INSERT)), rows)


def search_chunks(
    session: Session, knowledge_base_id: UUID, query_embedding: list[float], top_k: int
) -> list[RetrievedChunk]:
    """Finds the fragments of a base closest to a query, among the documents in force.

    Exists as the single read of retrieval; used by `search_knowledge`.

    Args:
        session: The open session to read through.
        knowledge_base_id: The only base to search in.
        query_embedding: The vector of the query.
        top_k: The maximum number of fragments.

    Returns:
        list[RetrievedChunk]: the fragments, closest first.
    """
    parameters = {
        "knowledge_base_id": str(knowledge_base_id),
        "query_embedding": json.dumps(query_embedding),
        "top_k": top_k,
    }
    sql = load_sql(DatabaseTable.KNOWLEDGE_CHUNKS, SqlOperation.SEARCH_BY_EMBEDDING)
    rows = session.execute(text(sql), parameters).mappings()
    return [RetrievedChunk.model_validate(dict(row)) for row in rows]
