-- Removes the steps of a flow so they can be written again, which also drops the steps a shorter
-- definition no longer has.
-- Consumed by save_flow in bia/orchestrations/repository.py.
DELETE FROM orchestration_steps
WHERE orchestration_id = CAST(:orchestration_id AS uuid);
