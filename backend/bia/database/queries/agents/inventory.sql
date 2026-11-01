-- Lists every agent with what it executes today and what it has cost, newest first.
-- Agents without runs, without an active version, or whose spec points to something missing keep
-- their row, with nulls or zeros.
-- Consumed by list_agent_inventory in bia/inventory/repository.py.

-- Totals are computed apart so joining the runs cannot multiply the other columns.
WITH run_totals AS (
    SELECT
        agent_id,
        COUNT(*) AS total_runs,
        SUM(total_cost) AS total_cost
    FROM runs
    GROUP BY agent_id
)
SELECT
    agents.id,
    agents.name,
    agents.owner_area,
    agents.kind,
    agents.status,
    agents.active_version_number,
    models.id AS model_id,
    models.name AS model_name,
    COALESCE(agent_versions.spec -> 'tool_names', CAST('[]' AS jsonb)) AS tool_names,
    knowledge_bases.id AS knowledge_base_id,
    knowledge_bases.name AS knowledge_base_name,
    COALESCE(run_totals.total_runs, 0) AS total_runs,
    COALESCE(run_totals.total_cost, 0) AS total_cost
FROM agents
LEFT JOIN agent_versions
    ON agent_versions.agent_id = agents.id
    AND agent_versions.version_number = agents.active_version_number
LEFT JOIN models
    ON models.id = CAST(agent_versions.spec ->> 'model_id' AS uuid)
LEFT JOIN knowledge_bases
    ON knowledge_bases.id = CAST(agent_versions.spec ->> 'knowledge_base_id' AS uuid)
LEFT JOIN run_totals
    ON run_totals.agent_id = agents.id
ORDER BY agents.created_at DESC, agents.id;
