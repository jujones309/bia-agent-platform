-- Moves an agent to another stage of its lifecycle.
-- Consumed by set_agent_status in bia/agents/repository.py.
UPDATE agents
SET
    status = :status,
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
