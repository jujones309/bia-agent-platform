-- Opens the audit record of an execution, before any of its steps happens.
-- Consumed by RunRecorder.start_run in bia/tracing/recorder.py.
-- Uses clock_timestamp() because started_at marks this call, not the enclosing transaction.
-- Moves started_at back by :already_elapsed_ms for work done before the run could exist.
INSERT INTO runs (agent_id, agent_version_id, origin, input, status, started_at)
VALUES (
    CAST(:agent_id AS uuid),
    CAST(:agent_version_id AS uuid),
    :origin,
    :input,
    :status,
    clock_timestamp() - make_interval(secs => CAST(:already_elapsed_ms AS double precision) / 1000)
)
RETURNING
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
    finished_at;
