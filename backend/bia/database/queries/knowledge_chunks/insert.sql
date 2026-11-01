-- Stores one fragment of a document with its embedding.
-- Consumed by replace_document_chunks in bia/rag/repository.py.
INSERT INTO knowledge_chunks (document_id, content, metadata, embedding)
VALUES (:document_id, :content, CAST(:metadata AS jsonb), CAST(:embedding AS vector));
