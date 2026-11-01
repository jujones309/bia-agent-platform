-- Retrieves one version from its identifier, so an open conversation keeps executing the version
-- it started with even if the agent activates another one.
-- Consumed by get_version_by_id in bia/agents/repository.py.
SELECT
    id,
    agent_id,
    version_number,
    spec,
    designer_justification,
    created_at
FROM agent_versions
WHERE id = CAST(:version_id AS uuid);
