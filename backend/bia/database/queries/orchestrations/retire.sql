-- Takes a flow out of the inventory while keeping its row and its steps as history.
-- Matches nothing if the flow does not exist or was already retired.
-- Consumed by retire_flow in bia/orchestrations/repository.py.
UPDATE orchestrations
SET retired_at = now()
WHERE id = CAST(:orchestration_id AS uuid)
    AND retired_at IS NULL
RETURNING id;
