-- Lists the tool catalog, optionally only the tools that can be assigned to agents.
-- Consumed by list_catalog_tools in bia/catalog/tools/repository.py.
SELECT
    id,
    name,
    description,
    parameters_schema,
    risk_level,
    is_active,
    created_at
FROM tools
WHERE is_active OR NOT :only_active
ORDER BY name;
