import pytest
from pydantic import ValidationError

from bia.catalog.tools.artifacts import CatalogTool, ToolResult


@pytest.mark.parametrize(
    "values", [{}, {"output": {"saldo_cop": 1}, "error": "No existe"}], ids=["neither", "both"]
)
def test_tool_result_requires_exactly_one_outcome(values: dict[str, object]) -> None:
    """Verifies the runtime can never receive an ambiguous result."""
    with pytest.raises(ValidationError, match="exactly one"):
        ToolResult(**values)


def test_tool_result_accepts_an_empty_output_as_success() -> None:
    """Verifies a tool with nothing to report is not confused with a missing outcome."""
    assert ToolResult(output={}).error is None


def test_catalog_tool_accepts_a_row_of_a_tool_that_left_the_code() -> None:
    """Verifies a retired tool's row does not break the listing of the whole catalog."""
    tool = CatalogTool.model_validate(
        {
            "id": "6f1c7c1e-0d6b-4a57-9a53-0f6f3f0a1b2c",
            "name": "retired_tool",
            "description": "Retired",
            "parameters_schema": {},
            "risk_level": "low",
            "is_active": False,
            "created_at": "2026-10-31T00:00:00Z",
        }
    )

    assert tool.name == "retired_tool"
