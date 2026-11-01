-- Retrieves one entry of the model catalog from its identifier.
-- Consumed by get_catalog_model in bia/catalog/models/repository.py.
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
WHERE id = :model_id;
