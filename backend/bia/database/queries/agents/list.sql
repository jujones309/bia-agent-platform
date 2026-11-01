-- Lists the registry of agents, newest first, without their embeddings.
-- Consumed by list_agents in bia/agents/repository.py.
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
ORDER BY created_at DESC, id;
