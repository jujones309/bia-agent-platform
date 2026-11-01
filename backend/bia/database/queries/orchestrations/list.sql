-- Lists the flows in force, ordered by name.
-- Consumed by list_orchestration_inventory in bia/inventory/repository.py.
SELECT
    id,
    name,
    description,
    orchestration_type
FROM orchestrations
WHERE retired_at IS NULL
ORDER BY name, id;
