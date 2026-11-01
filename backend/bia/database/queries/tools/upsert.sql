-- Writes one tool of the code registry to the catalog, creating or refreshing its row.
-- Consumed by upsert_catalog_tool in bia/catalog/tools/repository.py during the startup sync.
INSERT INTO tools (name, description, parameters_schema, risk_level, is_active)
VALUES (:name, :description, CAST(:parameters_schema AS jsonb), :risk_level, true)
ON CONFLICT (name) DO UPDATE SET
    description = EXCLUDED.description,
    parameters_schema = EXCLUDED.parameters_schema,
    risk_level = EXCLUDED.risk_level,
    is_active = true;
