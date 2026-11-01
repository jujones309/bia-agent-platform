-- Creates the ordered steps of each flow.
-- Applied by bia/database/migrate.py; read by the orchestration inventory.
CREATE TABLE IF NOT EXISTS orchestration_steps (
    -- uuid: identifier of the step.
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- uuid: flow the step belongs to.
    orchestration_id uuid NOT NULL REFERENCES orchestrations (id),
    -- integer: position within the flow, starting at 1.
    step_order integer NOT NULL,
    -- uuid: agent that executes the step.
    agent_id uuid NOT NULL REFERENCES agents (id),
    -- text: what context the step receives.
    receives_context text NOT NULL,
    -- text: what the step delivers to the next one.
    delivers_output text NOT NULL,
    UNIQUE (orchestration_id, step_order)
);

ALTER TABLE orchestration_steps ENABLE ROW LEVEL SECURITY;
