-- Creates the audit record of each step inside a run.
-- Applied by bia/database/migrate.py; written and read by bia/tracing/.
CREATE TABLE IF NOT EXISTS run_steps (
    -- uuid: identifier of the step.
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- uuid: run the step belongs to.
    run_id uuid NOT NULL REFERENCES runs (id),
    -- integer: position within the run, starting at 1.
    step_order integer NOT NULL,
    -- text: kind of step: llm_call, tool_call or retrieval.
    step_type text NOT NULL CHECK (step_type IN ('llm_call', 'tool_call', 'retrieval')),
    -- uuid: model used; null if the step did not call a model.
    model_id uuid REFERENCES models (id),
    -- uuid: tool used; null if the step did not call a tool.
    tool_id uuid REFERENCES tools (id),
    -- jsonb: what the step received.
    input jsonb NOT NULL,
    -- jsonb: what the step returned; null if it failed.
    output jsonb,
    -- integer: input tokens; 0 if the step did not call a model.
    input_tokens integer NOT NULL DEFAULT 0,
    -- integer: output tokens; 0 if the step did not call a model.
    output_tokens integer NOT NULL DEFAULT 0,
    -- numeric: cost of the step in USD.
    cost numeric(14, 8) NOT NULL DEFAULT 0,
    -- integer: duration of the step in milliseconds.
    latency_ms integer NOT NULL,
    -- text: error message; null if the step succeeded.
    error text,
    -- timestamptz: when the step was recorded.
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, step_order)
);

ALTER TABLE run_steps ENABLE ROW LEVEL SECURITY;
