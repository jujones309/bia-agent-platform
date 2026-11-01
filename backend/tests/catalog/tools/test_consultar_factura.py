import json
from pathlib import Path
from unittest.mock import sentinel

import pytest
from pydantic import ValidationError

from bia.catalog.tools.artifacts import ToolName
from bia.catalog.tools.consultar_factura import ConsultarFacturaTool


def test_run_returns_the_invoice_of_the_requested_customer() -> None:
    """Verifies the exact billing data of one customer of the real data file."""
    result = ConsultarFacturaTool().run({"numero_cliente": "100001"}, sentinel.context)

    assert result.error is None
    assert result.output == {
        "saldo_cop": 187450,
        "periodo": "2026-10",
        "consumo_kwh": 212,
        "fecha_limite": "2026-11-18",
    }


def test_output_can_be_sent_to_the_model_as_json() -> None:
    """Verifies dates do not stay as objects the runtime could not serialize."""
    result = ConsultarFacturaTool().run({"numero_cliente": "100001"}, sentinel.context)

    assert json.loads(json.dumps(result.output)) == result.output


def test_run_reports_an_unknown_customer_as_an_error_for_the_model() -> None:
    """Verifies a wrong number does not raise, so the agent can ask for it again."""
    result = ConsultarFacturaTool().run({"numero_cliente": "999999"}, sentinel.context)

    assert result.output is None
    assert "999999" in result.error


def test_data_file_covers_the_customers_the_demo_needs() -> None:
    """Verifies the plan's ten customers, and that the credit balance case exists."""
    tool = ConsultarFacturaTool()
    customers = [f"1000{number:02d}" for number in range(1, 11)]

    balances = [
        tool.run({"numero_cliente": number}, sentinel.context).output["saldo_cop"]
        for number in customers
    ]

    assert min(balances) < 0


def test_schema_requires_the_argument_that_run_reads() -> None:
    """Verifies the contract offered to the model matches what the tool needs."""
    tool = ConsultarFacturaTool()

    assert tool.name == ToolName.CONSULTAR_FACTURA
    assert tool.parameters_schema["required"] == ["numero_cliente"]
    assert "numero_cliente" in tool.parameters_schema["properties"]


def test_corrupt_data_fails_when_the_tool_is_built(tmp_path: Path) -> None:
    """Verifies bad data is caught at startup, not in a customer's conversation."""
    invoices_path = tmp_path / "facturas.json"
    invoices_path.write_text(json.dumps({"100001": {"saldo_cop": "mucho"}}), encoding="utf-8")

    with pytest.raises(ValidationError):
        ConsultarFacturaTool(invoices_path)
