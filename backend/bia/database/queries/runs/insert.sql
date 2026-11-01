-- Opens the audit record of an execution, before any of its steps happens.
-- Consumed by RunRecorder.start_run in bia/tracing/recorder.py.
-- Uses clock_timestamp() because started_at marks this call, not the enclosing transaction.
INSERT INTO runs (agent_id, agent_version_id, origin, input, status, started_at)
VALUES (
    CAST(:agent_id AS uuid),
    CAST(:agent_version_id AS uuid),
    :origin,
    :input,
    :status,
    clock_timestamp()
)
RETURNING
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
    finished_at;
