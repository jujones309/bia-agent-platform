-- Creates the documents ingested into each knowledge base; unique titles make ingestion idempotent.
-- Applied by bia/database/migrate.py; read and written by bia/rag/.
CREATE TABLE IF NOT EXISTS knowledge_documents (
    -- uuid: identifier of the document.
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- uuid: knowledge base the document belongs to.
    knowledge_base_id uuid NOT NULL REFERENCES knowledge_bases (id),
    -- text: title; the source the agent cites.
    title text NOT NULL,
    -- text: defines the chunking strategy: tariff, procedure or faq.
    document_type text NOT NULL CHECK (document_type IN ('tariff', 'procedure', 'faq')),
    -- date: when the content takes effect; null if not applicable.
    valid_from date,
    -- date: when the content stops applying; null if still in force.
    valid_until date,
    -- timestamptz: when the document was ingested.
    created_at timestamptz NOT NULL DEFAULT now(),
    -- timestamptz: when the document was taken out of the base; null while it is in force.
    retired_at timestamptz,
    UNIQUE (knowledge_base_id, title)
);

-- Brings databases created before the column existed up to date.
ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS retired_at timestamptz;

ALTER TABLE knowledge_documents ENABLE ROW LEVEL SECURITY;
