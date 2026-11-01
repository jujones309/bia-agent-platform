-- Retrieves one run by its identifier, so the frontend can open the trace of a playground answer.
-- Consumed by get_run in bia/tracing/repository.py.
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
WHERE id = CAST(:run_id AS uuid);
