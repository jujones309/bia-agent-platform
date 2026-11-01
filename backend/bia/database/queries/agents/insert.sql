-- Registers a new agent with its description embedding, pointing at its first version.
-- Consumed by insert_agent in bia/agents/repository.py.
INSERT INTO agents (
    name,
    description,
    owner_area,
    creator,
    status,
    kind,
    description_embedding,
    active_version_number
)
VALUES (
    :name,
    :description,
    :owner_area,
    :creator,
    :status,
    :kind,
    CAST(:description_embedding AS vector),
    :active_version_number
)
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
