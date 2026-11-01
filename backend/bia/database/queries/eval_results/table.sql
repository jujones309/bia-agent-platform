-- Creates the outcome of evaluating one case against one agent version.
-- Applied by bia/database/migrate.py; written by bia/evals/ and read by the publish gate.
CREATE TABLE IF NOT EXISTS eval_results (
    -- uuid: identifier of the result.
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- uuid: case evaluated.
    eval_case_id uuid NOT NULL REFERENCES eval_cases (id),
    -- uuid: version evaluated.
    agent_version_id uuid NOT NULL REFERENCES agent_versions (id),
    -- text: the agent's answer.
    output text NOT NULL,
    -- text: the judge's decision: pass or fail; a pass counts towards the publish gate.
    verdict text NOT NULL,
    -- numeric: the judge's score from 0 to 100; says how close the answer came.
    score numeric(5, 2) NOT NULL,
    -- text: why the judge decided that way.
    judge_reason text NOT NULL,
    -- timestamptz: when the case was evaluated.
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE eval_results ENABLE ROW LEVEL SECURITY;
