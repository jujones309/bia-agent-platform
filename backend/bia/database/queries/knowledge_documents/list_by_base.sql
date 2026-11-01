-- Lists the current documents of a knowledge base with how many fragments each one has, by title.
-- Consumed by list_documents in bia/rag/repository.py.

-- Counted apart so a document always keeps exactly one row.
WITH chunk_counts AS (
    SELECT
        document_id,
        COUNT(*) AS chunk_count
    FROM knowledge_chunks
    GROUP BY document_id
)
SELECT
    documents.id,
    documents.knowledge_base_id,
    documents.title,
    documents.document_type,
    documents.valid_from,
    documents.valid_until,
    COALESCE(chunk_counts.chunk_count, 0) AS chunk_count,
    documents.created_at
FROM knowledge_documents AS documents
LEFT JOIN chunk_counts
    ON chunk_counts.document_id = documents.id
WHERE documents.knowledge_base_id = CAST(:knowledge_base_id AS uuid)
    AND documents.retired_at IS NULL
ORDER BY documents.title, documents.id;
