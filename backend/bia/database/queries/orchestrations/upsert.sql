-- Registers a flow at its fixed identifier, or refreshes it and puts it back in force. It always
-- updates, even without changes, because the row lock makes a concurrent startup wait before
-- replacing the same steps.
-- Consumed by save_flow in bia/orchestrations/repository.py.
INSERT INTO orchestrations (id, name, description, orchestration_type)
VALUES (CAST(:orchestration_id AS uuid), :name, :description, :orchestration_type)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    orchestration_type = EXCLUDED.orchestration_type,
    retired_at = NULL;
