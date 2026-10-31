from fastapi.testclient import TestClient

from bia.api.main import app


def test_health_reports_ok_status() -> None:
    """Verifies the health endpoint answers 200 with the exact agreed body."""
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
