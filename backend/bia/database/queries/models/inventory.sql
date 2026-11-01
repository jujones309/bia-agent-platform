-- Lists every catalog model with how many agents use it and what it has consumed, ordered by name.
-- Models nobody uses keep their row, with zeros.
-- Consumed by list_model_inventory in bia/inventory/repository.py.

-- Agents that execute the model today; an archived agent no longer uses anything.
WITH agent_usage AS (
    SELECT
        CAST(agent_versions.spec ->> 'model_id' AS uuid) AS model_id,
        COUNT(*) AS agents_using
    FROM agents
    JOIN agent_versions
        ON agent_versions.agent_id = agents.id
        AND agent_versions.version_number = agents.active_version_number
    WHERE agents.status <> :archived_status
    GROUP BY CAST(agent_versions.spec ->> 'model_id' AS uuid)
),
-- Consumption comes from the steps, the only record that knows which model served each call.
step_usage AS (
    SELECT
        model_id,
        SUM(input_tokens) AS input_tokens,
        SUM(output_tokens) AS output_tokens,
        SUM(cost) AS total_cost
    FROM run_steps
    WHERE model_id IS NOT NULL
    GROUP BY model_id
)
SELECT
    models.id,
    models.name,
    models.provider,
    models.size,
    models.is_active,
    COALESCE(agent_usage.agents_using, 0) AS agents_using,
    COALESCE(step_usage.input_tokens, 0) AS input_tokens,
    COALESCE(step_usage.output_tokens, 0) AS output_tokens,
    COALESCE(step_usage.total_cost, 0) AS total_cost
FROM models
LEFT JOIN agent_usage
    ON agent_usage.model_id = models.id
LEFT JOIN step_usage
    ON step_usage.model_id = models.id
ORDER BY models.name, models.id;
