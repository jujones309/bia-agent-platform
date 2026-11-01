-- Creates the knowledge bases agents can retrieve from.
-- Applied by bia/database/migrate.py; read and written by bia/rag/.
CREATE TABLE IF NOT EXISTS knowledge_bases (
    -- uuid: identifier of the base; what an agent spec references.
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- text: visible name.
    name text NOT NULL,
    -- text: what knowledge the base contains.
    description text NOT NULL,
    -- timestamptz: when the base was created.
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE knowledge_bases ENABLE ROW LEVEL SECURITY;
