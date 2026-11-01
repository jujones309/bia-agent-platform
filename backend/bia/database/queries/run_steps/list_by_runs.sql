-- Lists the steps of several runs at once, in execution order within each run.
-- Consumed by list_steps_of_runs in bia/tracing/repository.py, avoiding one query per run.
SELECT
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
    created_at
FROM run_steps
WHERE run_id = ANY(CAST(:run_ids AS uuid[]))
ORDER BY run_id, step_order;
