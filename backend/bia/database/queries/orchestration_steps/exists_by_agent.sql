-- Tells whether an agent takes part in any flow, also in a retired one, so publishing neither
-- duplicates a flow declared by hand nor brings back one that a person retired.
-- Consumed by agent_has_flow in bia/orchestrations/repository.py.
SELECT EXISTS (
    SELECT 1
    FROM orchestration_steps
    WHERE agent_id = CAST(:agent_id AS uuid)
);
