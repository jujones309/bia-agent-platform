-- Registers a system agent at its fixed identifier, or refreshes its name and description if they
-- changed. Waits for a concurrent startup that is registering the same agent.
-- Consumed by upsert_system_agent in bia/agents/repository.py.
INSERT INTO agents (
    id,
    name,
    description,
    owner_area,
    creator,
    status,
    kind,
    active_version_number
)
VALUES (
    CAST(:agent_id AS uuid),
    :name,
    :description,
    :owner_area,
    :creator,
    :status,
    :kind,
    :active_version_number
)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    updated_at = now()
WHERE agents.name IS DISTINCT FROM EXCLUDED.name
    OR agents.description IS DISTINCT FROM EXCLUDED.description;
