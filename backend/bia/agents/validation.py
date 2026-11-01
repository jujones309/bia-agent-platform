from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.orm import Session

from bia.agents.artifacts import AgentSpec, AgentSpecPatch
from bia.catalog.models.artifacts import CatalogModel, ModelSize
from bia.catalog.models.repository import list_catalog_models
from bia.catalog.tools.artifacts import CatalogTool, ToolName
from bia.catalog.tools.repository import list_catalog_tools
from bia.rag.repository import KnowledgeBaseNotFoundError, get_knowledge_base


class InvalidAgentSpecError(ValueError):
    """Signals that a spec cannot become a version of an agent.

    Exists so bad content is told apart from infrastructure failures, with a message that says
    what to fix. Raised by this module and translated to a 422 by `bia/api/agents.py`; the
    designer will rely on it to retry an invalid proposal.
    """


def find_model_problems(model_id: UUID, models: list[CatalogModel]) -> list[str]:
    """Explains why a model cannot be assigned to a new version, if so.

    Exists as the designer's guarantee that it chooses and does not invent. Embedding models
    are rejected too, because the runtime could only fail when calling them for a chat.

    Args:
        model_id: The model the spec references.
        models: The whole model catalog, retired entries included.

    Returns:
        list[str]: the problems found; empty if the model can be assigned.
    """
    model = next((entry for entry in models if entry.id == model_id), None)
    if model is None:
        return [f"The model catalog has no entry with id {model_id}"]
    if not model.is_active:
        return [f"The model '{model.name}' ({model_id}) is retired"]
    if model.size is ModelSize.EMBEDDING:
        return [f"The model '{model.name}' ({model_id}) only generates embeddings"]
    return []


def find_tool_problems(tool_names: list[str], tools: list[CatalogTool]) -> list[str]:
    """Explains why the tools of a spec cannot be used, if so.

    Exists so an agent is never given a capability that does not exist; used for new versions
    and for rollbacks, since the runtime refuses to execute a spec with an unavailable tool.

    Args:
        tool_names: The tools the spec names.
        tools: The whole tool catalog, retired entries included.

    Returns:
        list[str]: one problem per unknown or retired tool; empty if all can be used.
    """
    active_by_name = {tool.name: tool.is_active for tool in tools}
    problems = []
    for name in tool_names:
        if name not in active_by_name:
            problems.append(f"The tool catalog has no tool named '{name}'")
        elif not active_by_name[name]:
            problems.append(f"The tool '{name}' is retired")
    return problems


def find_knowledge_problems(spec: AgentSpec, knowledge_base_exists: bool) -> list[str]:
    """Explains why the knowledge settings of a spec do not work together, if so.

    Exists because the tool and the base are useless apart: the tool would have nothing to read,
    and a base without the tool would silently never be consulted. Used for new versions.

    Args:
        spec: The spec about to be stored.
        knowledge_base_exists: Whether the base the spec references exists, if it has one.

    Returns:
        list[str]: the problems found; empty if the settings are consistent.
    """
    uses_tool = ToolName.BUSCAR_CONOCIMIENTO in spec.tool_names
    base_id = spec.knowledge_base_id
    if base_id is None and not uses_tool:
        return []
    if base_id is None:
        return [f"The tool '{ToolName.BUSCAR_CONOCIMIENTO}' needs a knowledge_base_id"]
    problems = [] if knowledge_base_exists else [f"There is no knowledge base with id {base_id}"]
    if not uses_tool:
        problems.append(f"A knowledge base needs the tool '{ToolName.BUSCAR_CONOCIMIENTO}'")
    return problems


def _knowledge_base_exists(session: Session, spec: AgentSpec) -> bool:
    """Checks whether the base a spec references is stored.

    Exists to keep the read apart from the rules of `find_knowledge_problems`; used by
    `validate_new_spec`.

    Args:
        session: The open session to read through.
        spec: The spec about to be stored.

    Returns:
        bool: whether the base exists; False if the spec references none.
    """
    if spec.knowledge_base_id is None:
        return False
    try:
        get_knowledge_base(session, spec.knowledge_base_id)
    except KnowledgeBaseNotFoundError:
        return False
    return True


def validate_new_spec(session: Session, spec: AgentSpec) -> None:
    """Rejects a spec that references anything unavailable in the catalogs.

    Exists as the only entrance of a spec to the registry; used when creating an agent or a
    version. Reports every problem at once, so they can all be fixed in one attempt.

    Args:
        session: The open session to read the catalogs through.
        spec: The spec about to be stored.

    Returns:
        None: the spec is valid if nothing is raised.

    Raises:
        InvalidAgentSpecError: If the model, a tool or the knowledge base cannot be used.
    """
    problems = [
        *find_model_problems(spec.model_id, list_catalog_models(session, only_active=False)),
        *find_tool_problems(spec.tool_names, list_catalog_tools(session, only_active=False)),
        *find_knowledge_problems(spec, _knowledge_base_exists(session, spec)),
    ]
    if problems:
        raise InvalidAgentSpecError("; ".join(problems))


def validate_rollback_spec(session: Session, spec: AgentSpec) -> None:
    """Rejects a rollback to a spec the runtime would refuse to execute.

    Exists because a rollback must leave the agent working. A retired model is allowed, unlike
    in a new version: retiring only closes it to new specs, and the runtime still runs it.

    Args:
        session: The open session to read the catalog through.
        spec: The spec of the version about to be activated.

    Returns:
        None: the spec can run if nothing is raised.

    Raises:
        InvalidAgentSpecError: If a tool cannot be used.
    """
    problems = find_tool_problems(spec.tool_names, list_catalog_tools(session, only_active=False))
    if problems:
        raise InvalidAgentSpecError("; ".join(problems))


def merge_spec_patch(spec: AgentSpec, patch: AgentSpecPatch) -> AgentSpec:
    """Applies a partial change to a spec and validates the outcome.

    Exists so edits go through the same rules as complete specs; used by `add_version`. A patch
    that changes nothing is an error, because it would add a version identical to the last one.

    Args:
        spec: The spec the change starts from.
        patch: The fields to change; only those sent in the request count.

    Returns:
        AgentSpec: the resulting spec.

    Raises:
        InvalidAgentSpecError: If the result is not a valid spec or equals the original.
    """
    values = {**spec.model_dump(), **patch.model_dump(exclude_unset=True)}
    try:
        merged = AgentSpec.model_validate(values)
    except ValidationError as error:
        raise InvalidAgentSpecError(_describe_validation_error(error)) from error
    if merged == spec:
        raise InvalidAgentSpecError("The change is identical to the active version")
    return merged


def _describe_validation_error(error: ValidationError) -> str:
    """Summarizes why a merged spec is invalid.

    Exists because pydantic's own text is long and links to its documentation; used by
    `merge_spec_patch`.

    Args:
        error: The validation error of the merged spec.

    Returns:
        str: one `field: reason` entry per problem, separated by semicolons.
    """
    return "; ".join(
        f"{'.'.join(str(part) for part in detail['loc'])}: {detail['msg']}"
        for detail in error.errors()
    )
