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
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE eval_cases ENABLE ROW LEVEL SECURITY;
