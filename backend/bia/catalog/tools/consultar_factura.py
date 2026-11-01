import json
from pathlib import Path

from bia.catalog.tools.artifacts import CustomerInvoice, RiskLevel, ToolName, ToolResult
from bia.catalog.tools.base import Tool, ToolContext

_INVOICES_PATH = Path(__file__).resolve().parent / "data" / "facturas.json"
_CUSTOMER_NUMBER_ARGUMENT = "numero_cliente"
_DESCRIPTION = (
    "Consulta la factura actual de un cliente a partir de su número de cliente. Devuelve el "
    "saldo en pesos colombianos, el período facturado, el consumo en kWh y la fecha límite "
    "de pago. Un saldo negativo es un saldo a favor del cliente."
)
_PARAMETERS_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        _CUSTOMER_NUMBER_ARGUMENT: {
            "type": "string",
            "description": "Número de cliente, tal como aparece en la factura.",
        },
    },
    "required": [_CUSTOMER_NUMBER_ARGUMENT],
    "additionalProperties": False,
}


def _load_invoices(path: Path) -> dict[str, CustomerInvoice]:
    """Reads the invoice data file, validating every invoice.

    Exists so corrupt data fails when the tool is built, not during a customer's
    conversation; used by `ConsultarFacturaTool`.

    Args:
        path: The JSON file that maps customer numbers to invoices.

    Returns:
        dict[str, CustomerInvoice]: the invoices by customer number.
    """
    raw_invoices = json.loads(path.read_text(encoding="utf-8"))
    return {
        customer_number: CustomerInvoice.model_validate(invoice)
        for customer_number, invoice in raw_invoices.items()
    }


class ConsultarFacturaTool(Tool):
    """Looks up the current invoice of a customer.

    Exists because balances are transactional data that RAG cannot answer. Reads fake
    invoices from a JSON file until a billing system is connected. Registered in
    `bia/catalog/tools/registry.py` and called by the runtime.
    """

    def __init__(self, invoices_path: Path = _INVOICES_PATH) -> None:
        """Initializes the tool, loading its invoices.

        Args:
            invoices_path (Path): The JSON file that holds the invoices.
        """
        self._invoices = _load_invoices(invoices_path)

    @property
    def name(self) -> ToolName:
        """Provides the name the model invokes and the spec references.

        Exists to implement the `Tool` contract.

        Returns:
            ToolName: the tool's name.
        """
        return ToolName.CONSULTAR_FACTURA

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

    def run(self, args: dict[str, object], _context: ToolContext) -> ToolResult:
        """Looks up the invoice of the requested customer.

        Exists as the tool's behavior. An unknown customer is an expected outcome, so the
        model receives it as an error and can ask for the number again.

        Args:
            args: The arguments, already validated against `parameters_schema`.
            _context: Unused; required by the `Tool` contract.

        Returns:
            ToolResult: the invoice as JSON-compatible data, or the error for the model.
        """
        customer_number = args[_CUSTOMER_NUMBER_ARGUMENT]
        invoice = self._invoices.get(customer_number)
        if invoice is None:
            return ToolResult(error=f"No existe un cliente con el número {customer_number}.")
        return ToolResult(output=invoice.model_dump(mode="json"))
