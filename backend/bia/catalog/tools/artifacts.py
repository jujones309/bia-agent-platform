from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from bia.tracing.artifacts import StepType


class ToolName(StrEnum):
    """The tools implemented by the platform.

    Exists so a tool is always one option of a closed set; consumed by the registry in
    `bia/catalog/tools/registry.py` and by each tool implementation.
    """

    CONSULTAR_FACTURA = "consultar_factura"
    BUSCAR_CONOCIMIENTO = "buscar_conocimiento"


class RiskLevel(StrEnum):
    """How sensitive the effect of a tool is.

    Exists to mirror the proposed values of `tools.risk_level`; declared by each tool and
    consumed by the designer and the inventories.
    """

    LOW = "low"  # only reads data
    MEDIUM = "medium"
    HIGH = "high"


class ToolResult(BaseModel):
    """Holds the outcome of one tool execution: either an output or an error.

    Exists so expected failures, such as an unknown customer, reach the model as
    information it can act on instead of breaking the loop. Also says how the runtime must
    trace the execution, including any model the tool called, since every LLM call is traced.
    Produced by `Tool.run` and consumed by the runtime.
    """

    output: dict[str, object] | None = None
    error: str | None = None
    step_type: StepType = StepType.TOOL_CALL
    model_id: UUID | None = None  # the model the tool called, if any
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost: Decimal = Field(default=Decimal(0), ge=0)

    @model_validator(mode="after")
    def _require_exactly_one_outcome(self) -> Self:
        """Rejects a result that has both an output and an error, or neither.

        Exists so the runtime never has to guess whether a tool succeeded; called by
        pydantic on construction.

        Returns:
            Self: the validated result.
        """
        if (self.output is None) == (self.error is None):
            raise ValueError("A tool result must have exactly one of output or error")
        return self


class CatalogTool(BaseModel):
    """Represents one entry of the curated tool catalog.

    Exists as the contract of a row of the `tools` table; consumed by the tools API and
    the designer. `name` is plain text, not `ToolName`, because a retired tool keeps its
    row after leaving the code.
    """

    id: UUID
    name: str
    description: str
    parameters_schema: dict[str, object]
    risk_level: RiskLevel
    is_active: bool
    created_at: datetime


class CustomerInvoice(BaseModel):
    """Describes the current invoice of a customer.

    Exists to validate the invoice data file on load and to define what `consultar_factura`
    returns. Field names are in Spanish because the model reads them to answer customers.
    """

    saldo_cop: int  # negative when the customer has a credit balance
    periodo: str  # billing month, as YYYY-MM
    consumo_kwh: int
    fecha_limite: date
