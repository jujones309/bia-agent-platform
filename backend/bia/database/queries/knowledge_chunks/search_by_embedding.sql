-- Finds the fragments of one knowledge base closest to a query, by cosine distance.
-- Only documents in force count, so an expired tariff is never retrieved, and a fragment below the
-- minimum similarity is not returned, so a question off topic can come back empty.
-- Consumed by search_chunks in bia/rag/repository.py.

-- The closest fragments of the base. Filtering by similarity out here, and not in this scan, keeps a
-- question off topic from making the vector index walk through the whole table looking for matches.
WITH nearest AS MATERIALIZED (
    SELECT
        chunks.id AS chunk_id,
        chunks.metadata ->> 'document' AS document,
        chunks.metadata ->> 'section' AS section,
        chunks.content,
        1 - (chunks.embedding <=> CAST(:query_embedding AS vector)) AS similarity
    FROM knowledge_chunks AS chunks
    JOIN knowledge_documents AS documents ON documents.id = chunks.document_id
    WHERE documents.knowledge_base_id = :knowledge_base_id
        AND (documents.valid_from IS NULL OR documents.valid_from <= CURRENT_DATE)
        AND (documents.valid_until IS NULL OR documents.valid_until >= CURRENT_DATE)
    ORDER BY chunks.embedding <=> CAST(:query_embedding AS vector), chunks.id
    LIMIT :top_k
)
SELECT chunk_id, document, section, content, similarity
FROM nearest
WHERE similarity >= :minimum_similarity
ORDER BY similarity DESC, chunk_id;
