-- Lists the registered flows, ordered by name.
-- Consumed by list_orchestration_inventory in bia/inventory/repository.py.
SELECT
    id,
    name,
    description,
    orchestration_type
FROM orchestrations
ORDER BY name, id;
