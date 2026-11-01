-- Creates the test cases an agent must pass before being published.
-- Applied by bia/database/migrate.py; read and written by bia/evals/.
CREATE TABLE IF NOT EXISTS eval_cases (
    -- uuid: identifier of the case.
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- uuid: agent the case evaluates.
    agent_id uuid NOT NULL REFERENCES agents (id),
    -- text: test message.
    input text NOT NULL,
    -- text: what the agent should do; what the judge compares against.
    expected_behavior text NOT NULL,
    -- text: how the case was created: generated or manual.
    origin text NOT NULL CHECK (origin IN ('generated', 'manual')),
    -- timestamptz: when the case was created.
    created_at timestamptz NOT NULL DEFAULT now(),
    -- timestamptz: when the case stopped counting for reports and the gate; null while it is in force.
    retired_at timestamptz
);

-- Brings databases created before the column existed up to date.
ALTER TABLE eval_cases ADD COLUMN IF NOT EXISTS retired_at timestamptz;

ALTER TABLE eval_cases ENABLE ROW LEVEL SECURITY;
