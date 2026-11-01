-- Lists the steps of every flow in execution order, with the agent, model and tools each one uses
-- today. A step whose agent has no active version, or whose model is missing, keeps its row.
-- Consumed by list_orchestration_inventory in bia/inventory/repository.py.
SELECT
    orchestration_steps.orchestration_id,
    orchestration_steps.step_order,
    orchestration_steps.agent_id,
    agents.name AS agent_name,
    agents.status AS agent_status,
    models.id AS model_id,
    models.name AS model_name,
    COALESCE(agent_versions.spec -> 'tool_names', CAST('[]' AS jsonb)) AS tool_names,
    orchestration_steps.receives_context,
    orchestration_steps.delivers_output
FROM orchestration_steps
JOIN agents
    ON agents.id = orchestration_steps.agent_id
LEFT JOIN agent_versions
    ON agent_versions.agent_id = agents.id
    AND agent_versions.version_number = agents.active_version_number
LEFT JOIN models
    ON models.id = CAST(agent_versions.spec ->> 'model_id' AS uuid)
ORDER BY orchestration_steps.orchestration_id, orchestration_steps.step_order;
