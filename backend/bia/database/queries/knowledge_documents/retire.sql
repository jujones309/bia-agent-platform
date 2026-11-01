-- Takes a document out of its base, keeping its row as the record that it existed.
-- Matches nothing if it is not a current document of that base.
-- Consumed by retire_document in bia/rag/repository.py.
UPDATE knowledge_documents
SET retired_at = now()
WHERE id = CAST(:document_id AS uuid)
    AND knowledge_base_id = CAST(:knowledge_base_id AS uuid)
    AND retired_at IS NULL
RETURNING id;
