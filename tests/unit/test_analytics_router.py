from uuid import uuid4

from fastapi.testclient import TestClient


def test_analyze_returns_503_when_no_model_version_is_configured(client: TestClient) -> None:
    response = client.post(
        "/analytics/sentiment/analyze",
        params={"organization_id": str(uuid4()), "product_id": str(uuid4())},
    )
    assert response.status_code == 503
    assert "sentiment model version" in response.json()["detail"]


def test_get_distribution_returns_503_when_no_model_version_is_configured(
    client: TestClient,
) -> None:
    response = client.get(
        "/analytics/sentiment",
        params={"organization_id": str(uuid4()), "product_id": str(uuid4())},
    )
    assert response.status_code == 503
