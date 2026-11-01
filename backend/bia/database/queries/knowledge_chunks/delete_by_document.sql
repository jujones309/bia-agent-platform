-- Removes the fragments of a document before writing those of its new version.
-- Consumed by replace_document_chunks in bia/rag/repository.py.
DELETE FROM knowledge_chunks
WHERE document_id = :document_id;
