from sqlalchemy import text
from sqlalchemy.orm import Session

from bia.database.queries import DatabaseTable, SqlOperation, load_sql
from bia.orchestrations.artifacts import Flow, FlowStep


def _insert_step(session: Session, flow: Flow, step_order: int, step: FlowStep) -> None:
    """Writes one step of a flow.

    Exists to keep the column mapping out of `save_flow`, which reads as the steps of a
    replacement.

    Args:
        session: The open session whose transaction contains the write.
        flow: The flow the step belongs to.
        step_order: The position of the step, starting at 1.
        step: The step to write.

    Returns:
        None: the row is written inside the session's transaction.
    """
    parameters = {
        "orchestration_id": str(flow.orchestration_id),
        "step_order": step_order,
        "agent_id": str(step.agent_id),
        "receives_context": step.receives_context,
        "delivers_output": step.delivers_output,
    }
    session.execute(
        text(load_sql(DatabaseTable.ORCHESTRATION_STEPS, SqlOperation.INSERT)), parameters
    )


def save_flow(session: Session, flow: Flow) -> None:
    """Registers a flow, or replaces what was registered under its identifier.

    Exists so the database can be brought to a definition any number of times; used by
    `bia/orchestrations/flows.py`.

    Args:
        session: The open session whose transaction contains the writes.
        flow: The flow to register.

    Returns:
        None: the flow and its steps are written inside the session's transaction.
    """
    identifier = {"orchestration_id": str(flow.orchestration_id)}
    session.execute(
        text(load_sql(DatabaseTable.ORCHESTRATIONS, SqlOperation.UPSERT)),
        {
            **identifier,
            "name": flow.name,
            "description": flow.description,
            "orchestration_type": flow.orchestration_type,
        },
    )
    session.execute(
        text(load_sql(DatabaseTable.ORCHESTRATION_STEPS, SqlOperation.DELETE_BY_ORCHESTRATION)),
        identifier,
    )
    for step_order, step in enumerate(flow.steps, start=1):
        _insert_step(session, flow, step_order, step)
