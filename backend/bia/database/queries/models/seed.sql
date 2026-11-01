-- Seeds the catalog with one large, one small and one embedding OpenAI model.
-- Applied by bia/database/migrate.py. Running it again refreshes prices without duplicating rows.
-- Prices: standard tier, short context, from developers.openai.com/api/docs/pricing (2026-10-31).
INSERT INTO models (
    name,
    provider,
    provider_model_id,
    size,
    input_cost_per_million,
    output_cost_per_million,
    context_window,
    recommended_use
)
VALUES
    (
        'GPT-6.1 Sol',
        'openai',
        'gpt-6.1-sol',
        'large',
        2.00,
        10.00,
        1050000,
        'Complex reasoning, agent design and multi-step tool use, where quality outweighs cost.'
    ),
    (
        'GPT-6 Luna',
        'openai',
        'gpt-6-luna',
        'small',
        0.10,
        0.50,
        1050000,
        'High-volume, well-scoped tasks such as customer questions and classification.'
    ),
    (
        'Text Embedding 3 Small',
        'openai',
        'text-embedding-3-small',
        'embedding',
        0.02,
        0,
        8192,
        'Embeddings of 1536 dimensions for knowledge retrieval and duplicate detection.'
    )
ON CONFLICT (provider, provider_model_id) DO UPDATE SET
    name = EXCLUDED.name,
    size = EXCLUDED.size,
    input_cost_per_million = EXCLUDED.input_cost_per_million,
    output_cost_per_million = EXCLUDED.output_cost_per_million,
    context_window = EXCLUDED.context_window,
    recommended_use = EXCLUDED.recommended_use;
