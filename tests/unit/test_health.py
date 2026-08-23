import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_liveness(client: TestClient) -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "Voxera API",
        "version": "0.1.0",
        "environment": "test",
        "components": {},
    }
    assert response.headers["x-request-id"]


def test_request_id_is_preserved(client: TestClient) -> None:
    response = client.get("/health/live", headers={"x-request-id": "test-request-id"})

    assert response.headers["x-request-id"] == "test-request-id"


def test_readiness_reports_configuration(client: TestClient) -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["components"] == {
        "configuration": {"status": "ok", "detail": None}
    }


def test_readiness_returns_503_when_database_is_unavailable(
    app: FastAPI,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unavailable() -> None:
        raise ConnectionError("test database failure")

    app.state.settings.check_database_readiness = True
    monkeypatch.setattr(app.state.database, "ping", unavailable)

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "error"
    assert response.json()["components"]["database"] == {
        "status": "error",
        "detail": "database unavailable",
    }
