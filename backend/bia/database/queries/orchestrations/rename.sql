-- Refreshes the name and description of a flow that follows the identity of its agent.
-- Matches nothing if the agent has no flow of its own, which is not an error.
-- Consumed by rename_flow in bia/orchestrations/repository.py.
UPDATE orchestrations
SET
    name = :name,
    description = :description
WHERE id = CAST(:orchestration_id AS uuid);
