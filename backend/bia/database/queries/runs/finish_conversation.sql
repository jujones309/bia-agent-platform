-- Closes an open conversation when the person finishes it. It succeeded if any turn got an answer.
-- Its latency adds up the steps instead of using the clock, because the time a person takes to
-- reply is not time the agent worked, and would distort the p50 of the agent.
-- Consumed by RunRecorder.finish_conversation in bia/tracing/recorder.py. Returns no row if the
-- run does not exist or was already closed.
-- Adds up what the run consumed and how long its steps took; a run without steps totals 0.
WITH step_totals AS (
    SELECT
        COALESCE(SUM(input_tokens + output_tokens), 0) AS total_tokens,
        COALESCE(SUM(cost), 0) AS total_cost,
        COALESCE(SUM(latency_ms), 0) AS latency_ms
    FROM run_steps
    WHERE run_id = CAST(:run_id AS uuid)
)
UPDATE runs
SET
    status = CASE WHEN runs.output IS NULL THEN :failed_status ELSE :succeeded_status END,
    error = CASE WHEN runs.output IS NULL THEN CAST(:no_answer_error AS text) END,
    total_tokens = step_totals.total_tokens,
    total_cost = step_totals.total_cost,
    latency_ms = step_totals.latency_ms,
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
    runs.error,
    runs.total_tokens,
    runs.total_cost,
    runs.latency_ms,
    runs.started_at,
    runs.finished_at;
