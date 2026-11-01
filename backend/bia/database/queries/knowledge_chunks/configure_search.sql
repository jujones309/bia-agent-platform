-- Chooses how the next search of a base reads the fragments, for the current transaction only, so it
-- is safe behind the transaction pooler. A small base is compared exactly, because the vector index
-- gives up before reaching the few fragments it has among those of other bases, and would silently
-- lose answers. A large one uses the index, scanning until it finds enough fragments of that base.
-- Consumed by search_chunks in bia/rag/repository.py.

-- How many fragments the searched base holds.
WITH base_size AS (
    SELECT count(*) AS chunk_count
    FROM knowledge_chunks AS chunks
    JOIN knowledge_documents AS documents ON documents.id = chunks.document_id
    WHERE documents.knowledge_base_id = :knowledge_base_id
)
SELECT
    set_config(
        'enable_indexscan',
        CASE WHEN chunk_count <= :exact_search_maximum_chunks THEN 'off' ELSE 'on' END,
        true
    ),
    set_config('hnsw.iterative_scan', 'strict_order', true)
FROM base_size;
