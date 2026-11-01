-- Creates a knowledge base that agent specs can reference.
-- Consumed by insert_knowledge_base in bia/rag/repository.py.
INSERT INTO knowledge_bases (name, description)
VALUES (:name, :description)
RETURNING id, name, description, created_at;
