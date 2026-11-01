from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from bia.agents.artifacts import AgentVersion
from bia.agents.repository import get_active_version
from bia.catalog.models.artifacts import CatalogModel
from bia.catalog.models.repository import CatalogModelNotFoundError, get_catalog_model
from bia.catalog.tools.artifacts import CatalogTool
from bia.catalog.tools.repository import list_catalog_tools


class AgentConfigurationError(ValueError):
    """Signals that a spec references something that cannot be executed anymore.

    Exists so a stale spec fails clearly before any tokens are spent. Raised by
    `load_agent_execution` and translated to a 409 by `bia/api/runtime.py`.
    """


@dataclass(frozen=True)
class AgentExecution:
    """Gathers everything needed to execute one version of an agent.

    Exists so the loop needs no database reads of its own; built by `load_agent_execution`
    and consumed by `AgentRunner`.
    """

    version: AgentVersion
    model: CatalogModel
    tools: list[CatalogTool]


def _resolve_tools(session: Session, tool_names: list[str]) -> list[CatalogTool]:
    """Finds the catalog entries of the tools a spec names.

    Exists so a retired or unknown tool stops the execution instead of silently leaving the
    agent without a capability its prompt relies on; used by `load_agent_execution`.

    Args:
        session: The open session to read through.
        tool_names: The names listed in the spec.

    Returns:
        list[CatalogTool]: the active entries, in the order of the spec.

    Raises:
        AgentConfigurationError: If a name has no active entry.
    """
    active_tools = {tool.name: tool for tool in list_catalog_tools(session, only_active=True)}
    missing = [name for name in tool_names if name not in active_tools]
    if missing:
        raise AgentConfigurationError(f"The spec names unavailable tools: {', '.join(missing)}")
    return [active_tools[name] for name in tool_names]


def load_agent_execution(session: Session, agent_id: UUID) -> AgentExecution:
    """Loads the active version of an agent and resolves its references.

    Exists to do all the reading in one short transaction before the long-running loop. A
    retired model still runs, because being retired only closes it to new agents.

    Args:
        session: The open session to read through.
        agent_id: The agent to execute.

    Returns:
        AgentExecution: the version with its model and tools.

    Raises:
        ActiveVersionNotFoundError: If the agent does not exist or has no active version.
        AgentConfigurationError: If the spec references an unavailable model or tool.
    """
    version = get_active_version(session, agent_id)
    try:
        model = get_catalog_model(session, version.spec.model_id)
    except CatalogModelNotFoundError as error:
        raise AgentConfigurationError(str(error)) from error
    return AgentExecution(version, model, _resolve_tools(session, version.spec.tool_names))
