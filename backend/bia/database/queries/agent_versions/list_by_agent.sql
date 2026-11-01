-- Lists the history of an agent's versions, oldest first.
-- Consumed by list_versions in bia/agents/repository.py.
SELECT
    id,
    agent_id,
    version_number,
    spec,
    designer_justification,
    created_at
FROM agent_versions
WHERE agent_id = CAST(:agent_id AS uuid)
ORDER BY version_number;
