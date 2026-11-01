from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class OrchestrationType(StrEnum):
    """The shapes a flow of agents can take.

    Exists so `orchestrations.orchestration_type` holds a closed set; set by the definitions of
    `bia/orchestrations/flows.py` and exposed by the orchestration inventory.
    """

    SINGLE_AGENT = "single_agent"  # one agent resolves everything with its tools
    SEQUENTIAL = "sequential"  # each agent hands its output to the next one


@dataclass(frozen=True)
class FlowStep:
    """Declares one step of a flow.

    Exists to document who works at each point and what passes between them; built by
    `bia/orchestrations/flows.py` and written by `save_flow`, which assigns its position.
    """

    agent_id: UUID
    receives_context: str
    delivers_output: str


@dataclass(frozen=True)
class Flow:
    """Declares a flow of agents, with its steps in execution order.

    Exists so a flow is registered as a whole under a fixed identifier, which makes registering
    it again harmless; built by `bia/orchestrations/flows.py` and written by `save_flow`.
    """

    orchestration_id: UUID
    name: str
    description: str
    orchestration_type: OrchestrationType
    steps: tuple[FlowStep, ...]
