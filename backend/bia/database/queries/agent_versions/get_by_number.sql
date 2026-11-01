-- Retrieves one version of an agent from its number.
-- Consumed by get_version in bia/agents/repository.py.
SELECT
    id,
    agent_id,
    version_number,
    spec,
    designer_justification,
    created_at
FROM agent_versions
WHERE agent_id = CAST(:agent_id AS uuid)
    AND version_number = :version_number;
