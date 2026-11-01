-- Creates the retrievable fragments of each document; deleted with it so it can be re-ingested.
-- Applied by bia/database/migrate.py; written and searched by bia/rag/.
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    -- uuid: identifier of the fragment.
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- uuid: document of origin.
    document_id uuid NOT NULL REFERENCES knowledge_documents (id) ON DELETE CASCADE,
    -- text: text retrieved and handed to the agent.
    content text NOT NULL,
    -- jsonb: data used to cite the fragment, such as its section and document.
    metadata jsonb NOT NULL,
    -- vector: embedding of the content for semantic search.
    embedding vector(1536) NOT NULL,
    -- timestamptz: when the fragment was generated.
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Keeps the semantic search fast as the fragments grow; see search_by_embedding.sql.
CREATE INDEX IF NOT EXISTS knowledge_chunks_embedding_index ON knowledge_chunks USING hnsw (embedding vector_cosine_ops);

ALTER TABLE knowledge_chunks ENABLE ROW LEVEL SECURITY;
