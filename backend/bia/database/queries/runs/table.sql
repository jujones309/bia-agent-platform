-- Creates the audit record of each complete agent execution.
-- Applied by bia/database/migrate.py; written and read by bia/tracing/.
CREATE TABLE IF NOT EXISTS runs (
    -- uuid: identifier of the run.
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- uuid: agent executed.
    agent_id uuid NOT NULL REFERENCES agents (id),
    -- uuid: exact version executed.
    agent_version_id uuid NOT NULL REFERENCES agent_versions (id),
    -- text: what triggered the run.
    origin text NOT NULL,
    -- text: input received.
    input text NOT NULL,
    -- text: final answer; null while running or if it failed.
    output text,
    -- text: execution state.
    status text NOT NULL,
    -- text: why the run failed; null unless it failed.
    error text,
    -- integer: sum of the tokens of its steps.
    total_tokens integer NOT NULL DEFAULT 0,
    -- numeric: sum in USD of the cost of its steps.
    total_cost numeric(14, 8) NOT NULL DEFAULT 0,
    -- integer: total duration in milliseconds; null until finished.
    latency_ms integer,
    -- timestamptz: when the run started.
    started_at timestamptz NOT NULL DEFAULT now(),
    -- timestamptz: when the run finished; null while running.
    finished_at timestamptz
);

ALTER TABLE runs ENABLE ROW LEVEL SECURITY;
