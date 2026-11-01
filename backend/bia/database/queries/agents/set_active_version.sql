-- Changes the version an agent executes.
-- Consumed by set_active_version in bia/agents/repository.py.
UPDATE agents
SET
    active_version_number = :version_number,
    updated_at = now()
WHERE id = CAST(:agent_id AS uuid)
RETURNING
    id,
    name,
    description,
    owner_area,
    creator,
    status,
    kind,
    active_version_number,
    created_at,
    updated_at;
