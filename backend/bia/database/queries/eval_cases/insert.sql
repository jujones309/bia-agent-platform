-- Stores one test case of an agent, generated or written by a person.
-- Consumed by insert_case in bia/evals/repository.py.
-- Uses clock_timestamp() so the cases of one transaction keep the order in which they were written.
INSERT INTO eval_cases (agent_id, input, expected_behavior, origin, created_at)
VALUES (CAST(:agent_id AS uuid), :input, :expected_behavior, :origin, clock_timestamp())
RETURNING id, agent_id, input, expected_behavior, origin, created_at;
