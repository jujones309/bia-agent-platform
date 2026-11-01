-- Appends a version to an agent, at the next number of its sequence. Versions are only ever
-- inserted, which is what keeps them immutable.
-- Consumed by insert_version in bia/agents/repository.py, with the agent's row already locked
-- or just created.
INSERT INTO agent_versions (agent_id, version_number, spec, designer_justification)
VALUES (
    CAST(:agent_id AS uuid),
    (
        SELECT COALESCE(MAX(version_number), 0) + 1
        FROM agent_versions
        WHERE agent_id = CAST(:agent_id AS uuid)
    ),
    CAST(:spec AS jsonb),
    :designer_justification
)
RETURNING
    id,
    agent_id,
    version_number,
    spec,
    designer_justification,
    created_at;
