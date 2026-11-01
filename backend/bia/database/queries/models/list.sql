-- Lists the model catalog, optionally only the models that can be chosen for new agents.
-- Consumed by list_catalog_models in bia/catalog/models/repository.py.
SELECT
    id,
    name,
    provider,
    provider_model_id,
    size,
    input_cost_per_million,
    output_cost_per_million,
    context_window,
    recommended_use,
    is_active,
    created_at
FROM models
WHERE is_active OR NOT :only_active
ORDER BY name;
