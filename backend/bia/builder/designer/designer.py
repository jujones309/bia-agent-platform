import json
import logging
from dataclasses import dataclass

from sqlalchemy import Connection, Engine
from sqlalchemy.orm import Session

from bia.agents.artifacts import AgentDraft
from bia.agents.registry import create_agent
from bia.agents.validation import InvalidAgentSpecError, parse_spec, validate_new_spec
from bia.builder.artifacts import (
    AgentDesign,
    AgentProposal,
    AgentProposalRequest,
    DesignerJustification,
    ProposedAgent,
)
from bia.builder.system_agents import DESIGNER_AGENT_ID
from bia.builder.system_run import SystemAgentRun
from bia.catalog.models.artifacts import CatalogModel, ModelSize
from bia.catalog.models.repository import list_catalog_models
from bia.catalog.tools.artifacts import CatalogTool
from bia.catalog.tools.repository import list_catalog_tools
from bia.database.connection import database_session
from bia.providers.artifacts import ChatMessage, MessageRole
from bia.rag.artifacts import KnowledgeBase
from bia.rag.repository import list_knowledge_bases
from bia.runtime.execution import load_agent_execution
from bia.tracing.recorder import RunRecorder

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 2  # the first design and one retry
_MODEL_FIELDS = {
    "id",
    "name",
    "size",
    "input_cost_per_million",
    "output_cost_per_million",
    "context_window",
    "recommended_use",
}
_TOOL_FIELDS = {"name", "description", "risk_level"}
_KNOWLEDGE_BASE_FIELDS = {"id", "name", "description"}
_NON_SPEC_FIELDS = {"name", "justification"}


class InvalidProposalError(InvalidAgentSpecError):
    """Signals that the designer did not produce a valid spec, even after its retry.

    Exists so the failure says it was the model's and not the person's: they sent no spec. Raised
    by `design_agent` and translated to a 502 by `bia/api/builder.py`.
    """


@dataclass(frozen=True)
class DesignCatalog:
    """Gathers what the designer may choose from.

    Exists so the catalogs are read in one short transaction before the LLM call; built by
    `_load_catalog` and consumed by `design_agent`.
    """

    models: list[CatalogModel]
    tools: list[CatalogTool]
    knowledge_bases: list[KnowledgeBase]


def _load_catalog(session: Session) -> DesignCatalog:
    """Reads what can be assigned to a new agent.

    Exists so the designer is never offered anything `validate_new_spec` would reject, such as an
    embedding model; used by `propose_agent`.

    Args:
        session: The open session to read through.

    Returns:
        DesignCatalog: the chat models, the active tools and the knowledge bases.
    """
    models = list_catalog_models(session, only_active=True)
    return DesignCatalog(
        models=[model for model in models if model.size is not ModelSize.EMBEDDING],
        tools=list_catalog_tools(session, only_active=True),
        knowledge_bases=list_knowledge_bases(session),
    )


def _build_designer_input(description: str, catalog: DesignCatalog) -> str:
    """Writes the data the designer's prompt expects.

    Exists to keep the need and the catalogs apart from the versioned instructions; used by
    `design_agent`.

    Args:
        description: The described need.
        catalog: What the designer may choose from.

    Returns:
        str: the JSON document of the user message.
    """
    payload = {
        "necesidad": description,
        "modelos": [
            model.model_dump(mode="json", include=_MODEL_FIELDS) for model in catalog.models
        ],
        "herramientas": [
            tool.model_dump(mode="json", include=_TOOL_FIELDS) for tool in catalog.tools
        ],
        "bases_de_conocimiento": [
            base.model_dump(mode="json", include=_KNOWLEDGE_BASE_FIELDS)
            for base in catalog.knowledge_bases
        ],
    }
    return json.dumps(payload, ensure_ascii=False)


def _validate_design(bind: Engine | Connection, design: AgentDesign) -> AgentProposal:
    """Checks the designer's answer against the spec rules and the catalogs.

    Exists because the designer chooses and does not invent: an unknown reference is a hard error.
    Used by `design_agent`.

    Args:
        bind: The database handle to read the catalogs through.
        design: The answer of the designer.

    Returns:
        AgentProposal: the design, as a proposal that can become an agent.

    Raises:
        InvalidAgentSpecError: If the design is invalid; its message says what to fix.
    """
    if not design.name.strip():
        raise InvalidAgentSpecError("name: must not be empty")
    spec = parse_spec(design.model_dump(exclude=_NON_SPEC_FIELDS))
    with database_session(bind) as session:
        validate_new_spec(session, spec)
    return AgentProposal(name=design.name, spec=spec, justification=design.justification)


def _build_correction(design: AgentDesign, problems: str) -> list[ChatMessage]:
    """Builds the turns that show the designer why its answer was rejected.

    Exists so the retry can fix the concrete problems instead of guessing; used by `design_agent`.

    Args:
        design: The rejected answer.
        problems: What the validation found.

    Returns:
        list[ChatMessage]: the rejected answer followed by the problems.
    """
    correction = json.dumps({"problemas_de_validacion": problems}, ensure_ascii=False)
    return [
        ChatMessage(role=MessageRole.ASSISTANT, content=design.model_dump_json()),
        ChatMessage(role=MessageRole.USER, content=correction),
    ]


def design_agent(
    run: SystemAgentRun,
    bind: Engine | Connection,
    description: str,
    catalog: DesignCatalog,
) -> AgentProposal:
    """Asks the designer for a spec, retrying once if it is invalid.

    Exists to guarantee that whatever leaves the designer can become an agent; used by
    `propose_agent`.

    Args:
        run: The open run of the designer.
        bind: The database handle to validate through.
        description: The described need.
        catalog: What the designer may choose from.

    Returns:
        AgentProposal: the validated proposal.

    Raises:
        ProviderError: If a model call fails.
        InvalidProposalError: If the retry is invalid too.
    """
    messages = run.initial_messages(_build_designer_input(description, catalog))
    problems = ""
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        design = run.ask(messages, AgentDesign)
        try:
            return _validate_design(bind, design)
        except InvalidAgentSpecError as error:
            problems = str(error)
            logger.warning("Design attempt %d was rejected: %s", attempt, problems)
            messages = [*messages, *_build_correction(design, problems)]
    raise InvalidProposalError(f"The designer produced no valid spec: {problems}")


def _render_justification(justification: DesignerJustification) -> str:
    """Writes a justification as the text stored in the agent's version.

    Exists because `agent_versions.designer_justification` is text; used by `propose_agent`.

    Args:
        justification: The reasons behind each decision.

    Returns:
        str: one `decision: reason` line per decision.
    """
    return "\n".join(f"{name}: {reason}" for name, reason in justification.model_dump().items())


def propose_agent(bind: Engine | Connection, request: AgentProposalRequest) -> ProposedAgent:
    """Designs an agent for a need and creates it in draft.

    Exists as the step of the builder that follows the duplicate check; used by the builder API.
    Reads happen in short transactions, so no connection stays open during LLM calls. The
    designer's run ends before the agent is created: if creating it fails, nothing is left half
    done and the design stays in the trace.

    Args:
        bind: The database handle to read, write and trace through.
        request: The described need and who will own the agent.

    Returns:
        ProposedAgent: the new draft agent, with the reasons behind its spec.

    Raises:
        ActiveVersionNotFoundError: If the designer is not registered.
        AgentConfigurationError: If the designer's spec references an unavailable model.
        EmbeddingModelUnavailableError: If the catalog has no active embedding model.
        ProviderError: If a model call fails.
        InvalidAgentSpecError: If the designer produced no valid spec.
    """
    with database_session(bind) as session:
        execution = load_agent_execution(session, DESIGNER_AGENT_ID)
        catalog = _load_catalog(session)
    with SystemAgentRun(RunRecorder(bind), execution, request.description) as run:
        proposal = design_agent(run, bind, request.description, catalog)
        run.finish(proposal.model_dump_json())
    draft = AgentDraft(
        name=proposal.name,
        description=request.description,
        owner_area=request.owner_area,
        creator=request.creator,
        spec=proposal.spec,
    )
    agent = create_agent(bind, draft, _render_justification(proposal.justification))
    return ProposedAgent(agent=agent, justification=proposal.justification)
