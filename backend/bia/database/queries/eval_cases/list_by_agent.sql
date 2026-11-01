-- Lists the test cases of an agent, oldest first, so reports keep a stable order.
-- Consumed by list_cases in bia/evals/repository.py.
SELECT id, agent_id, input, expected_behavior, origin, created_at
FROM eval_cases
WHERE agent_id = CAST(:agent_id AS uuid)
ORDER BY created_at, id;
