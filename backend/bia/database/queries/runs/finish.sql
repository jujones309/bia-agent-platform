-- Closes a running execution, deriving its totals from the steps actually recorded.
-- Consumed by RunRecorder.finish_run in bia/tracing/recorder.py. Returns no row if the run
-- does not exist or was already closed, so a closed record can never be rewritten.
-- Adds up what the run consumed; a run without steps totals 0.
WITH step_totals AS (
    SELECT
        COALESCE(SUM(input_tokens + output_tokens), 0) AS total_tokens,
        COALESCE(SUM(cost), 0) AS total_cost
    FROM run_steps
    WHERE run_id = CAST(:run_id AS uuid)
)
UPDATE runs
SET
    output = :output,
    status = :status,
    total_tokens = step_totals.total_tokens,
    total_cost = step_totals.total_cost,
    latency_ms = CAST(EXTRACT(EPOCH FROM clock_timestamp() - runs.started_at) * 1000 AS integer),
    finished_at = clock_timestamp()
FROM step_totals
WHERE runs.id = CAST(:run_id AS uuid) AND runs.status = :running_status
RETURNING
    runs.id,
    runs.agent_id,
    runs.agent_version_id,
    runs.origin,
    runs.input,
    runs.output,
    runs.status,
    runs.total_tokens,
    runs.total_cost,
    runs.latency_ms,
    runs.started_at,
    runs.finished_at;
