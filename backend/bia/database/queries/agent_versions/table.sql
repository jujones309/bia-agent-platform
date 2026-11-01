-- Creates the immutable versions of each agent's spec.
-- Applied by bia/database/migrate.py; written by bia/agents/ and read by bia/runtime/.
CREATE TABLE IF NOT EXISTS agent_versions (
    -- uuid: identifier of the version.
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- uuid: agent the version belongs to.
    agent_id uuid NOT NULL REFERENCES agents (id),
    -- integer: sequence number within the agent, starting at 1.
    version_number integer NOT NULL,
    -- jsonb: declarative spec executed by the runtime.
    spec jsonb NOT NULL,
    -- text: why the designer proposed this spec; null if the version was manual.
    designer_justification text,
    -- timestamptz: when the version was created.
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (agent_id, version_number)
);

ALTER TABLE agent_versions ENABLE ROW LEVEL SECURITY;
