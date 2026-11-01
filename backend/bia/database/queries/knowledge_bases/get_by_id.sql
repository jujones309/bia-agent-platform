-- Retrieves one knowledge base, to check a reference before using it.
-- Consumed by get_knowledge_base in bia/rag/repository.py.
SELECT id, name, description, created_at
FROM knowledge_bases
WHERE id = :knowledge_base_id;
