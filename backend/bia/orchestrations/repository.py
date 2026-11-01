from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from bia.database.queries import DatabaseTable, SqlOperation, load_sql
from bia.orchestrations.artifacts import Flow, FlowStep


class OrchestrationNotFoundError(LookupError):
    """Signals that no flow in force has the requested identifier.

    Exists so retiring a wrong or already retired flow fails clearly. Raised by `retire_flow` and
    translated to a 404 by `bia/api/orchestrations.py`.
    """


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


def retire_flow(session: Session, orchestration_id: UUID) -> None:
    """Takes a flow out of the inventory, keeping its row and its steps.

    Exists so the record that a flow existed survives its removal; used by
    `retire_registered_flow`.

    Args:
        session: The open session whose transaction contains the write.
        orchestration_id: The flow to retire.

    Returns:
        None: the flow is retired inside the session's transaction.

    Raises:
        OrchestrationNotFoundError: If no flow in force has that identifier.
    """
    sql = load_sql(DatabaseTable.ORCHESTRATIONS, SqlOperation.RETIRE)
    parameters = {"orchestration_id": str(orchestration_id)}
    if session.execute(text(sql), parameters).one_or_none() is None:
        raise OrchestrationNotFoundError(f"There is no flow in force with id {orchestration_id}")


def rename_flow(session: Session, orchestration_id: UUID, name: str, description: str) -> None:
    """Refreshes the name and description of a flow, if it exists.

    Exists so a flow that follows the identity of its agent does not keep an old name; used by
    `rename_single_agent_flow`.

    Args:
        session: The open session whose transaction contains the write.
        orchestration_id: The flow to refresh.
        name: The new name.
        description: The new description.

    Returns:
        None: the row, if any, is written inside the session's transaction.
    """
    parameters = {
        "orchestration_id": str(orchestration_id),
        "name": name,
        "description": description,
    }
    session.execute(text(load_sql(DatabaseTable.ORCHESTRATIONS, SqlOperation.RENAME)), parameters)


def agent_has_flow(session: Session, agent_id: UUID) -> bool:
    """Tells whether an agent takes part in any flow, also in a retired one.

    Exists so publishing neither duplicates a flow declared by hand nor brings back one that a
    person retired; used by `register_single_agent_flow`.

    Args:
        session: The open session to read through.
        agent_id: The agent to look up.

    Returns:
        bool: True if a step of any flow names the agent.
    """
    sql = load_sql(DatabaseTable.ORCHESTRATION_STEPS, SqlOperation.EXISTS_BY_AGENT)
    return session.execute(text(sql), {"agent_id": str(agent_id)}).scalar_one()
