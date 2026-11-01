-- Lists the most recent runs of an agent that ended with an answer, from one origin only. Failed
-- runs have no answer to judge; their rate is already in the metrics of the agent.
-- Consumed by list_succeeded_runs in bia/tracing/repository.py.
SELECT
    id,
    agent_id,
    agent_version_id,
    origin,
    input,
    output,
    status,
    error,
    total_tokens,
    total_cost,
    latency_ms,
    started_at,
    finished_at
FROM runs
WHERE agent_id = CAST(:agent_id AS uuid)
    AND origin = :origin
    AND status = :status
ORDER BY started_at DESC
LIMIT :limit;
