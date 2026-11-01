-- Lists the most recent result of each case for one agent version: a new eval run replaces what
-- the gate reads, while older results stay as history.
-- Consumed by list_latest_results in bia/evals/repository.py.
SELECT DISTINCT ON (eval_case_id)
    id,
    eval_case_id,
    agent_version_id,
    output,
    verdict,
    score,
    judge_reason,
    created_at
FROM eval_results
WHERE agent_version_id = CAST(:agent_version_id AS uuid)
ORDER BY eval_case_id, created_at DESC;
