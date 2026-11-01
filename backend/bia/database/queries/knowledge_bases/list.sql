-- Lists the knowledge bases, ordered by name, so the designer can only assign one that exists.
-- Consumed by list_knowledge_bases in bia/rag/repository.py.
SELECT id, name, description, created_at
FROM knowledge_bases
ORDER BY name, id;
