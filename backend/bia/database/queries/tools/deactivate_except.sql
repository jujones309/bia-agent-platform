-- Retires the catalog tools that are no longer in the code registry. Rows are kept because
-- past run steps reference them.
-- Consumed by deactivate_catalog_tools_except in bia/catalog/tools/repository.py.
UPDATE tools
SET is_active = false
WHERE is_active AND name <> ALL(CAST(:registered_names AS text[]));
