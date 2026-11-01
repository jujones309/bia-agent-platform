import logging

from bia.catalog.models.repository import EmbeddingModelUnavailableError
from bia.catalog.tools.artifacts import RiskLevel, ToolName, ToolResult
from bia.catalog.tools.base import Tool, ToolContext
from bia.providers.base import ProviderError
from bia.rag.artifacts import DEFAULT_TOP_K, KnowledgeSearchResult
from bia.rag.repository import KnowledgeBaseNotFoundError
from bia.rag.retrieval import search_knowledge
from bia.tracing.artifacts import StepType

logger = logging.getLogger(__name__)

_QUERY_ARGUMENT = "consulta"
_DESCRIPTION = (
    "Busca en la base de conocimiento del agente los fragmentos más relevantes para una pregunta "
    "sobre tarifas, procedimientos o preguntas frecuentes. Cada fragmento trae su documento y su "
    "sección: cítalos en la respuesta. Una lista vacía significa que no hay información vigente. "
    "No sirve para datos de un cliente en particular."
)
_PARAMETERS_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        _QUERY_ARGUMENT: {
            "type": "string",
            "minLength": 1,
            "description": "La pregunta en lenguaje natural, con todo su contexto.",
        },
    },
    "required": [_QUERY_ARGUMENT],
    "additionalProperties": False,
}
_NO_KNOWLEDGE_BASE_ERROR = "Este agente no tiene una base de conocimiento asignada."
_SEARCH_FAILED_ERROR = "La búsqueda en la base de conocimiento no está disponible en este momento."


def _to_tool_result(search: KnowledgeSearchResult) -> ToolResult:
    """Converts a search to what the model reads and the trace records.

    Exists to keep the translation apart from the error handling of `run`.

    Args:
        search: The outcome of the search.

    Returns:
        ToolResult: a retrieval step with the fragments and the cost of the embedding.
    """
    return ToolResult(
        output={"chunks": [chunk.model_dump(mode="json") for chunk in search.chunks]},
        step_type=StepType.RETRIEVAL,
        model_id=search.model_id,
        input_tokens=search.usage.input_tokens,
        output_tokens=search.usage.output_tokens,
        cost=search.cost,
    )


class BuscarConocimientoTool(Tool):
    """Searches the knowledge base assigned to the agent that calls it.

    Exists so agents answer from Bia's documents and can cite them. The base comes from the
    spec, never from the model, so an agent cannot read a base it was not given. Registered in
    `bia/catalog/tools/registry.py` and called by the runtime.
    """

    @property
    def name(self) -> ToolName:
        """Provides the name the model invokes and the spec references.

        Exists to implement the `Tool` contract.

        Returns:
            ToolName: the tool's name.
        """
        return ToolName.BUSCAR_CONOCIMIENTO

    @property
    def description(self) -> str:
        """Provides the text the model and the designer use to decide when to call the tool.

        Exists to implement the `Tool` contract.

        Returns:
            str: what the tool does.
        """
        return _DESCRIPTION

    @property
    def parameters_schema(self) -> dict[str, object]:
        """Provides the JSON Schema of the tool's arguments.

        Exists to implement the `Tool` contract.

        Returns:
            dict[str, object]: the JSON Schema.
        """
        return _PARAMETERS_SCHEMA

    @property
    def risk_level(self) -> RiskLevel:
        """Provides how sensitive the tool's effect is.

        Exists to implement the `Tool` contract. It is low because the tool only reads.

        Returns:
            RiskLevel: the tool's risk level.
        """
        return RiskLevel.LOW

    def run(self, args: dict[str, object], context: ToolContext) -> ToolResult:
        """Searches the base of the agent for the requested question.

        Exists as the tool's behavior. A failed search is an expected outcome, so the model can
        tell the user it could not check; the detail goes to the operators' logs.

        Args:
            args: The arguments, already validated against `parameters_schema`.
            context: The execution, which says which base to search and how to reach it.

        Returns:
            ToolResult: a retrieval step with the fragments, or the error for the model.
        """
        if context.knowledge_base_id is None:
            return ToolResult(error=_NO_KNOWLEDGE_BASE_ERROR, step_type=StepType.RETRIEVAL)
        try:
            search = search_knowledge(
                context.bind, context.knowledge_base_id, args[_QUERY_ARGUMENT], DEFAULT_TOP_K
            )
        except (ProviderError, EmbeddingModelUnavailableError, KnowledgeBaseNotFoundError) as error:
            logger.warning("Knowledge search failed: %s", error)
            return ToolResult(error=_SEARCH_FAILED_ERROR, step_type=StepType.RETRIEVAL)
        return _to_tool_result(search)
