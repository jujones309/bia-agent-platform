-- Creates the curated catalog of models an agent may use.
-- Applied by bia/database/migrate.py; read by bia/catalog/models/ and the builder's designer.
CREATE TABLE IF NOT EXISTS models (
    -- uuid: catalog identifier of the model; what an agent spec references.
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- text: readable name shown in the inventories.
    name text NOT NULL,
    -- text: provider that serves the model.
    provider text NOT NULL,
    -- text: exact identifier the provider's API expects.
    provider_model_id text NOT NULL,
    -- text: category used to choose a model: large, small or embedding.
    size text NOT NULL CHECK (size IN ('large', 'small', 'embedding')),
    -- numeric: USD per 1M input tokens.
    input_cost_per_million numeric(12, 6) NOT NULL,
    -- numeric: USD per 1M output tokens; 0 for embedding models.
    output_cost_per_million numeric(12, 6) NOT NULL,
    -- integer: maximum tokens accepted in one call.
    context_window integer NOT NULL,
    -- text: when to use the model; read by the designer to justify its choice.
    recommended_use text NOT NULL,
    -- boolean: whether the model can be chosen for new agents.
    is_active boolean NOT NULL DEFAULT true,
    -- timestamptz: when the model entered the catalog.
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (provider, provider_model_id)
);

ALTER TABLE models ENABLE ROW LEVEL SECURITY;
