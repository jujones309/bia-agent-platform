import argparse
import logging
from uuid import UUID, uuid5

from sqlalchemy.orm import Session

from bia.agents.artifacts import Agent
from bia.agents.repository import get_agent
from bia.builder.system_agents import (
    CASE_GENERATOR_AGENT_ID,
    DESIGNER_AGENT_ID,
    DUPLICATE_JUDGE_AGENT_ID,
    EVAL_JUDGE_AGENT_ID,
)
from bia.database.connection import database_session, get_engine
from bia.orchestrations.artifacts import Flow, FlowStep, OrchestrationType
from bia.orchestrations.repository import agent_has_flow, rename_flow, retire_flow, save_flow
from bia.settings.config import get_settings

logger = logging.getLogger(__name__)

BUILDER_FLOW_ID = UUID("7c2a9e41-3b6d-4d18-a5f0-6e1b8c0d2f01")
BILLING_FLOW_ID = UUID("7c2a9e41-3b6d-4d18-a5f0-6e1b8c0d2f02")
_SINGLE_AGENT_FLOWS_NAMESPACE = UUID("7c2a9e41-3b6d-4d18-a5f0-6e1b8c0d2f03")

_BUILDER_FLOW = Flow(
    orchestration_id=BUILDER_FLOW_ID,
    name="Agent Builder",
    description="Convierte una necesidad en lenguaje natural en un agente listo para publicar.",
    orchestration_type=OrchestrationType.SEQUENTIAL,
    steps=(
        FlowStep(
            agent_id=DUPLICATE_JUDGE_AGENT_ID,
            receives_context="La necesidad y hasta 3 agentes publicados parecidos.",
            delivers_output="El veredicto de duplicado y el agente candidato, si lo hay.",
        ),
        FlowStep(
            agent_id=DESIGNER_AGENT_ID,
            receives_context="La necesidad y los catálogos de modelos, herramientas y bases.",
            delivers_output="La spec del agente nuevo, con la justificación de cada decisión.",
        ),
        FlowStep(
            agent_id=CASE_GENERATOR_AGENT_ID,
            receives_context="La spec del agente.",
            delivers_output="Los casos de prueba, cada uno con su comportamiento esperado.",
        ),
        FlowStep(
            agent_id=EVAL_JUDGE_AGENT_ID,
            receives_context="La respuesta del agente a cada caso y el comportamiento esperado.",
            delivers_output="Veredicto, puntaje y razón por caso, que alimentan el gate.",
        ),
    ),
)


class ProtectedFlowError(ValueError):
    """Signals that a flow belongs to the platform and cannot be retired.

    Exists because the next startup would register the flow of the Agent Builder again anyway.
    Raised by `retire_registered_flow` and translated to a 409 by `bia/api/orchestrations.py`.
    """


def sync_builder_flow(session: Session) -> None:
    """Makes the orchestration registry reflect the flow of the Agent Builder.

    Exists at application startup, in `bia/api/main.py`, instead of in the migration seeds, because
    its steps reference the system agents and those are registered at startup too.

    Args:
        session: The open session whose transaction contains the sync.

    Returns:
        None: the flow is written inside the session's transaction.
    """
    save_flow(session, _BUILDER_FLOW)
    logger.info("Synced flow '%s' with %d steps", _BUILDER_FLOW.name, len(_BUILDER_FLOW.steps))


def register_billing_flow(session: Session, agent_id: UUID) -> None:
    """Registers the flow of the billing assistant: one agent that resolves everything with tools.

    Exists apart from `sync_builder_flow` because this agent is created through the Builder, so its
    identifier depends on the database; used by `main`.

    Args:
        session: The open session whose transaction contains the write.
        agent_id: The billing assistant of this database.

    Returns:
        None: the flow is written inside the session's transaction.

    Raises:
        AgentNotFoundError: If no agent has that identifier.
    """
    agent = get_agent(session, agent_id)
    flow = Flow(
        orchestration_id=BILLING_FLOW_ID,
        name="Asistente de facturación",
        description="Responde dudas de facturación con un solo agente y dos herramientas.",
        orchestration_type=OrchestrationType.SINGLE_AGENT,
        steps=(
            FlowStep(
                agent_id=agent.id,
                receives_context="La pregunta del cliente.",
                delivers_output="La respuesta final, con los datos de la factura o la cita.",
            ),
        ),
    )
    save_flow(session, flow)
    logger.info("Registered flow '%s' with agent '%s'", flow.name, agent.name)


def _single_agent_flow_id(agent_id: UUID) -> UUID:
    """Derives the identifier of the flow an agent gets when published.

    Exists so the flow of an agent can be found again from the agent alone, without a new column;
    used by `register_single_agent_flow` and `rename_single_agent_flow`.

    Args:
        agent_id: The agent the flow belongs to.

    Returns:
        UUID: always the same identifier for that agent.
    """
    return uuid5(_SINGLE_AGENT_FLOWS_NAMESPACE, str(agent_id))


def register_single_agent_flow(session: Session, agent: Agent) -> None:
    """Registers the flow of a newly published agent, unless it already takes part in one.

    Exists so every published agent appears in the orchestration inventory without declaring
    anything; used by `publish_agent`. An agent that is in any flow, also a retired one, is left
    alone, so a flow declared by hand is not duplicated and a retired one does not come back.

    Args:
        session: The open session whose transaction contains the write.
        agent: The agent being published.

    Returns:
        None: the flow, if needed, is written inside the session's transaction.
    """
    if agent_has_flow(session, agent.id):
        return
    flow = Flow(
        orchestration_id=_single_agent_flow_id(agent.id),
        name=agent.name,
        description=agent.description,
        orchestration_type=OrchestrationType.SINGLE_AGENT,
        steps=(
            FlowStep(
                agent_id=agent.id,
                receives_context="El mensaje de la persona.",
                delivers_output="La respuesta final del agente.",
            ),
        ),
    )
    save_flow(session, flow)
    logger.info("Registered single-agent flow for agent %s", agent.id)


def rename_single_agent_flow(session: Session, agent: Agent) -> None:
    """Makes the automatic flow of an agent follow its current name and description.

    Exists because that flow copies them when it is registered; used by `update_identity`. A flow
    declared by hand keeps its own texts.

    Args:
        session: The open session whose transaction contains the write.
        agent: The agent, with its new identity.

    Returns:
        None: the flow, if any, is written inside the session's transaction.
    """
    rename_flow(session, _single_agent_flow_id(agent.id), agent.name, agent.description)


def retire_registered_flow(session: Session, orchestration_id: UUID) -> None:
    """Retires a flow, unless it belongs to the platform.

    Exists as the rule behind `DELETE /orchestrations/{id}`.

    Args:
        session: The open session whose transaction contains the write.
        orchestration_id: The flow to retire.

    Returns:
        None: the flow is retired inside the session's transaction.

    Raises:
        ProtectedFlowError: If it is the flow of the Agent Builder.
        OrchestrationNotFoundError: If no flow in force has that identifier.
    """
    if orchestration_id == BUILDER_FLOW_ID:
        raise ProtectedFlowError(f"The flow '{_BUILDER_FLOW.name}' belongs to the platform")
    retire_flow(session, orchestration_id)
    logger.info("Retired flow %s", orchestration_id)


def main() -> None:
    """Registers the billing flow in the configured database.

    Exists as the command-line entrypoint:
    `uv run python -m bia.orchestrations.flows --billing-agent-id <id>`.

    Returns:
        None: the database is updated in place.
    """
    parser = argparse.ArgumentParser(description="Registers the billing assistant's flow.")
    parser.add_argument("--billing-agent-id", type=UUID, required=True)
    arguments = parser.parse_args()
    logging.basicConfig(level=get_settings().log_level)
    with database_session(get_engine()) as session:
        register_billing_flow(session, arguments.billing_agent_id)


if __name__ == "__main__":
    main()
