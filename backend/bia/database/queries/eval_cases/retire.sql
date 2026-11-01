-- Takes a case out of the reports and the gate, keeping its row and its results as history.
-- Matches nothing if the case is not a current case of that agent.
-- Consumed by retire_case in bia/evals/repository.py.
UPDATE eval_cases
SET retired_at = now()
WHERE id = CAST(:eval_case_id AS uuid)
    AND agent_id = CAST(:agent_id AS uuid)
    AND retired_at IS NULL
RETURNING id;
