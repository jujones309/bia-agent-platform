from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Connection, Engine

from bia.catalog.tools.artifacts import RiskLevel, ToolName, ToolResult


class UnknownToolError(ValueError):
    """Signals that a tool name has no implementation.

    Exists to name the rejected value and the valid options. Raised by `get_tool`.
    """


@dataclass(frozen=True)
class ToolContext:
    """Holds what a tool receives from the execution instead of from the model.

    Exists so a model can never choose what the spec decides, like the knowledge base to read.
    Built by `AgentRunner` and passed to every `Tool.run`.
    """

    bind: Engine | Connection  # the database handle of the execution
    knowledge_base_id: UUID | None  # the base assigned in the spec, if any


class Tool(ABC):
    """Defines what every tool an agent may call must provide.

    Exists so the runtime and the catalog sync work with any tool without knowing its
    implementation. Implemented in `bia/catalog/tools/` and resolved through the registry.
    """

    @property
    @abstractmethod
    def name(self) -> ToolName:
        """Provides the name the model invokes and the spec references.

        Exists to identify the tool in the registry and in the catalog.

        Returns:
            ToolName: the tool's name.
        """

    @property
    @abstractmethod
    def description(self) -> str:
        """Provides the text the model and the designer use to decide when to call the tool.

        Exists because the name alone does not tell them what the tool is for.

        Returns:
            str: what the tool does.
        """

    @property
    @abstractmethod
    def parameters_schema(self) -> dict[str, object]:
        """Provides the JSON Schema of the tool's arguments.

        Exists so the model knows what to send and the runtime can validate it.

        Returns:
            dict[str, object]: the JSON Schema.
        """

    @property
    @abstractmethod
    def risk_level(self) -> RiskLevel:
        """Provides how sensitive the tool's effect is.

        Exists so the designer and the inventories can weigh the tool before assigning it.

        Returns:
            RiskLevel: the tool's risk level.
        """

    @abstractmethod
    def run(self, args: dict[str, object], context: ToolContext) -> ToolResult:
        """Executes the tool.

        Exists as the single entrypoint the runtime calls. Expected failures are returned
        as an error result, not raised.

        Args:
            args: The arguments, already validated against `parameters_schema` by the caller.
            context: What the execution provides, which the model cannot influence.

        Returns:
            ToolResult: the output, or the error to show the model.
        """
