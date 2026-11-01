-- Writes one step of a flow.
-- Consumed by save_flow in bia/orchestrations/repository.py.
INSERT INTO orchestration_steps (
    orchestration_id,
    step_order,
    agent_id,
    receives_context,
    delivers_output
)
VALUES (
    CAST(:orchestration_id AS uuid),
    :step_order,
    CAST(:agent_id AS uuid),
    :receives_context,
    :delivers_output
);
