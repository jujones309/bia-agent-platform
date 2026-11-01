-- Creates the curated catalog of tools agents may call, synced from the code registry.
-- Applied by bia/database/migrate.py; read and upserted by bia/catalog/tools/.
CREATE TABLE IF NOT EXISTS tools (
    -- uuid: identifier of the tool.
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- text: name the model invokes and the spec references.
    name text NOT NULL UNIQUE,
    -- text: what the tool does; the model and the designer decide from this text.
    description text NOT NULL,
    -- jsonb: JSON Schema of the tool's arguments.
    parameters_schema jsonb NOT NULL,
    -- text: how sensitive the tool's effect is.
    risk_level text NOT NULL,
    -- boolean: whether the tool can be assigned to agents.
    is_active boolean NOT NULL DEFAULT true,
    -- timestamptz: when the tool entered the catalog.
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE tools ENABLE ROW LEVEL SECURITY;
