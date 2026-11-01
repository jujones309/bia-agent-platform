-- Changes the name, description and area of an agent. The embedding only changes together with the
-- description: a null parameter keeps the current vector.
-- Consumed by update_agent_identity in bia/agents/repository.py.
UPDATE agents
SET
    name = :name,
    description = :description,
    owner_area = :owner_area,
    description_embedding = COALESCE(CAST(:description_embedding AS vector), description_embedding),
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
