-- Aggregates the runs of one agent. Starts from agents so an agent without runs still gets
-- a row and an unknown agent gets none.
-- Consumed by get_agent_metrics in bia/tracing/repository.py.
-- The p50 and the error rate only consider finished runs: running ones have no latency or outcome.
SELECT
    agents.id AS agent_id,
    COUNT(runs.id) AS total_runs,
    COALESCE(SUM(runs.total_cost), 0) AS total_cost,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY runs.latency_ms) AS latency_p50_ms,
    CAST(COUNT(runs.id) FILTER (WHERE runs.status = :failed_status) AS double precision)
        / NULLIF(COUNT(runs.finished_at), 0) AS error_rate
FROM agents
LEFT JOIN runs ON runs.agent_id = agents.id
WHERE agents.id = CAST(:agent_id AS uuid)
GROUP BY agents.id;
