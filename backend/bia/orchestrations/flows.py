import argparse
import logging
from uuid import UUID

from sqlalchemy.orm import Session

from bia.agents.repository import get_agent
from bia.builder.system_agents import (
    CASE_GENERATOR_AGENT_ID,
    DESIGNER_AGENT_ID,
    DUPLICATE_JUDGE_AGENT_ID,
    EVAL_JUDGE_AGENT_ID,
)
from bia.database.connection import database_session, get_engine
from bia.orchestrations.artifacts import Flow, FlowStep, OrchestrationType
from bia.orchestrations.repository import save_flow
from bia.settings.config import get_settings

logger = logging.getLogger(__name__)

BUILDER_FLOW_ID = UUID("7c2a9e41-3b6d-4d18-a5f0-6e1b8c0d2f01")
BILLING_FLOW_ID = UUID("7c2a9e41-3b6d-4d18-a5f0-6e1b8c0d2f02")

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
