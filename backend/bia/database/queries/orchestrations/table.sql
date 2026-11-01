-- Creates the registry of flows that combine agents.
-- Applied by bia/database/migrate.py; read by the orchestration inventory.
CREATE TABLE IF NOT EXISTS orchestrations (
    -- uuid: identifier of the flow.
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- text: name shown in the inventory.
    name text NOT NULL,
    -- text: what the flow achieves.
    description text NOT NULL,
    -- text: shape of the flow.
    orchestration_type text NOT NULL,
    -- timestamptz: when the flow was registered.
    created_at timestamptz NOT NULL DEFAULT now(),
    -- timestamptz: when the flow was taken out of the inventory; null while it is in force.
    retired_at timestamptz
);

-- Brings databases created before the column existed up to date.
ALTER TABLE orchestrations ADD COLUMN IF NOT EXISTS retired_at timestamptz;

ALTER TABLE orchestrations ENABLE ROW LEVEL SECURITY;
