-- Retrieves one agent of the registry, without its embedding.
-- Consumed by get_agent in bia/agents/repository.py.
SELECT
    id,
    name,
    description,
    owner_area,
    creator,
    status,
    kind,
    active_version_number,
    created_at,
    updated_at
FROM agents
WHERE id = CAST(:agent_id AS uuid);
