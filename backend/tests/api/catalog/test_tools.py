from datetime import UTC, datetime
from unittest.mock import sentinel
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from bia.api.catalog import tools as tools_router
from bia.api.dependencies import get_session
from bia.api.main import app
from bia.catalog.tools.artifacts import CatalogTool, RiskLevel
from bia.catalog.tools.consultar_factura import ConsultarFacturaTool


def _catalog_entry() -> CatalogTool:
    """Builds the catalog entry of the real tool, as the repository would return it.

    Returns:
        CatalogTool: the entry.
    """
    tool = ConsultarFacturaTool()
    return CatalogTool(
        id=uuid4(),
        name=tool.name,
        description=tool.description,
        parameters_schema=tool.parameters_schema,
        risk_level=RiskLevel.LOW,
        is_active=True,
        created_at=datetime.now(UTC),
    )


@pytest.mark.parametrize(
    ("params", "expected_only_active"), [({}, False), ({"only_active": True}, True)]
)
def test_list_returns_the_catalog_and_forwards_the_filter(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    params: dict[str, bool],
    expected_only_active: bool,
) -> None:
    """Verifies the body exposes what a person needs and the filter reaches the catalog."""
    filters: list[bool] = []
    entry = _catalog_entry()
    app.dependency_overrides[get_session] = lambda: sentinel.session
    monkeypatch.setattr(
        tools_router,
        "list_catalog_tools",
        lambda _session, only_active: filters.append(only_active) or [entry],
    )

    response = api_client.get("/tools", params=params)

    assert response.status_code == 200
    assert filters == [expected_only_active]
    assert response.json()[0]["name"] == "consultar_factura"
    assert response.json()[0]["parameters_schema"]["required"] == ["numero_cliente"]


def test_tools_require_credentials() -> None:
    """Verifies the catalog stays behind the shared password."""
    assert TestClient(app).get("/tools").status_code == 401
