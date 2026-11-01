-- Adds up the cost of the runs started in the current calendar month, in UTC.
-- Consumed by get_inventory_summary in bia/inventory/repository.py.
SELECT COALESCE(SUM(total_cost), 0) AS total_cost
FROM runs
WHERE started_at >= date_trunc('month', now(), 'UTC');
