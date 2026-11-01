-- Lists the most recent runs, optionally only those of one agent.
-- Consumed by list_runs in bia/tracing/repository.py.
SELECT
    id,
    agent_id,
    agent_version_id,
    origin,
    input,
    output,
    status,
    total_tokens,
    total_cost,
    latency_ms,
    started_at,
    finished_at
FROM runs
WHERE CAST(:agent_id AS uuid) IS NULL OR agent_id = CAST(:agent_id AS uuid)
ORDER BY started_at DESC
LIMIT :limit;
