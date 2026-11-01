-- Finds the published agents of employees closest to a need, by cosine distance. Drafts are left
-- out because nobody can reuse them yet, and system agents because they are parts of the platform.
-- Consumed by find_candidates in bia/builder/duplicates/search.py.
SELECT
    id AS agent_id,
    name,
    description,
    1 - (description_embedding <=> CAST(:query_embedding AS vector)) AS similarity
FROM agents
WHERE status = :status
    AND kind = :kind
    AND description_embedding IS NOT NULL
ORDER BY description_embedding <=> CAST(:query_embedding AS vector), id
LIMIT :limit;
