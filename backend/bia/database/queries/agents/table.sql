-- Creates the registry of agents: their stable identity, while configuration lives in agent_versions.
-- Applied by bia/database/migrate.py; read and written by bia/agents/ and bia/builder/duplicates/.
CREATE TABLE IF NOT EXISTS agents (
    -- uuid: identifier of the agent.
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- text: name shown in the inventories.
    name text NOT NULL,
    -- text: the need it covers; the text compared by duplicate detection.
    description text NOT NULL,
    -- text: Bia area responsible for the agent.
    owner_area text NOT NULL,
    -- text: person who created the agent.
    creator text NOT NULL,
    -- text: lifecycle state: draft, testing, published or archived.
    status text NOT NULL CHECK (status IN ('draft', 'testing', 'published', 'archived')),
    -- text: user (created by employees) or system (part of the platform).
    kind text NOT NULL CHECK (kind IN ('user', 'system')),
    -- vector: embedding of the description for duplicate search; null until generated.
    description_embedding vector(1536),
    -- integer: number of the current version; null before the first. A number, not a foreign key, to avoid a cycle with agent_versions.
    active_version_number integer,
    -- timestamptz: when the agent was registered.
    created_at timestamptz NOT NULL DEFAULT now(),
    -- timestamptz: last modification of the record.
    updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE agents ENABLE ROW LEVEL SECURITY;
