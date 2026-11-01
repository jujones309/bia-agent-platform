-- Stores the outcome of evaluating one case against one agent version.
-- Consumed by insert_result in bia/evals/repository.py.
-- Uses clock_timestamp() because the gate reads the latest result of a case by this column.
INSERT INTO eval_results (
    eval_case_id,
    agent_version_id,
    output,
    verdict,
    score,
    judge_reason,
    created_at
)
VALUES (
    CAST(:eval_case_id AS uuid),
    CAST(:agent_version_id AS uuid),
    :output,
    :verdict,
    :score,
    :judge_reason,
    clock_timestamp()
)
RETURNING id, eval_case_id, agent_version_id, output, verdict, score, judge_reason, created_at;
