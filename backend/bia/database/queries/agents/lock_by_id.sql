-- Retrieves one agent and locks its row until the transaction ends, so concurrent edits of the
-- same agent cannot take the same version number or build on an outdated spec.
-- Consumed by lock_agent in bia/agents/repository.py.
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
WHERE id = CAST(:agent_id AS uuid)
FOR UPDATE;
