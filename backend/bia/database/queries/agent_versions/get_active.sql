-- Retrieves the version an agent currently executes. Returns no row if the agent does not
-- exist or has no active version yet.
-- Consumed by get_active_version in bia/agents/repository.py.
SELECT
    agent_versions.id,
    agent_versions.agent_id,
    agent_versions.version_number,
    agent_versions.spec,
    agent_versions.designer_justification,
    agent_versions.created_at
FROM agent_versions
JOIN agents
    ON agents.id = agent_versions.agent_id
    AND agents.active_version_number = agent_versions.version_number
WHERE agents.id = CAST(:agent_id AS uuid);
