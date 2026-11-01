-- Appends a step to a running execution, at the next position of that run.
-- Consumed by RunRecorder.add_step in bia/tracing/recorder.py. Returns no row if the run does
-- not exist or was already closed, so the totals of a closed run stay true.
-- Selects the run only if it can still receive steps.
WITH open_run AS (
    SELECT id
    FROM runs
    WHERE id = CAST(:run_id AS uuid) AND status = :running_status
)
INSERT INTO run_steps (
    run_id,
    step_order,
    step_type,
    model_id,
    tool_id,
    input,
    output,
    input_tokens,
    output_tokens,
    cost,
    latency_ms,
    error
)
SELECT
    open_run.id,
    (SELECT COALESCE(MAX(step_order), 0) + 1 FROM run_steps WHERE run_id = open_run.id),
    CAST(:step_type AS text),
    CAST(:model_id AS uuid),
    CAST(:tool_id AS uuid),
    CAST(:input AS jsonb),
    CAST(:output AS jsonb),
    CAST(:input_tokens AS integer),
    CAST(:output_tokens AS integer),
    CAST(:cost AS numeric),
    CAST(:latency_ms AS integer),
    CAST(:error AS text)
FROM open_run
RETURNING
    id,
    run_id,
    step_order,
    step_type,
    model_id,
    tool_id,
    input,
    output,
    input_tokens,
    output_tokens,
    cost,
    latency_ms,
    error,
    created_at;
