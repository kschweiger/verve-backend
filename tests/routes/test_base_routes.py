from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    print(data)
    assert data["status"] == "healthy"
    assert data["database"] == "healthy"
    assert data["object_store"] == "healthy"
