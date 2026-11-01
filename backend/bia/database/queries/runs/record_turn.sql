-- Brings an open conversation up to date after one of its turns, so its answer, tokens and cost
-- are visible without waiting for it to be finished, even if nobody ever finishes it.
-- Consumed by RunRecorder.record_turn in bia/tracing/recorder.py. Returns no row if the run does
-- not exist or was already closed. A turn without an answer keeps the previous one.
-- Adds up what the run consumed so far; a run without steps totals 0.
WITH step_totals AS (
    SELECT
        COALESCE(SUM(input_tokens + output_tokens), 0) AS total_tokens,
        COALESCE(SUM(cost), 0) AS total_cost
    FROM run_steps
    WHERE run_id = CAST(:run_id AS uuid)
)
UPDATE runs
SET
    output = COALESCE(CAST(:output AS text), runs.output),
    total_tokens = step_totals.total_tokens,
    total_cost = step_totals.total_cost
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
    runs.error,
    runs.total_tokens,
    runs.total_cost,
    runs.latency_ms,
    runs.started_at,
    runs.finished_at;
