-- Creates a document or refreshes the one with the same title, which also locks its row.
-- Consumed by upsert_document in bia/rag/repository.py; makes ingestion idempotent per document.
INSERT INTO knowledge_documents (knowledge_base_id, title, document_type, valid_from, valid_until)
VALUES (:knowledge_base_id, :title, :document_type, :valid_from, :valid_until)
ON CONFLICT (knowledge_base_id, title) DO UPDATE SET
    document_type = EXCLUDED.document_type,
    valid_from = EXCLUDED.valid_from,
    valid_until = EXCLUDED.valid_until,
    created_at = now()
RETURNING id;
