"""Health and service info tests."""

from fastapi.testclient import TestClient


def test_root_endpoint(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Muquissi"
    assert data["status"] == "operational"


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"
    assert data["database"]["connected"] is True
    assert data["database"]["engine"] == "sqlite"
    assert "ollama" in data
    assert isinstance(data["ollama"]["available"], bool)


def test_info_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/info")
    assert response.status_code == 200
    data = response.json()
    assert data["phase"] == 10
    assert data["phase_name"] == "Aplicação Desktop"
    assert data["modules"]["core"] == "ready"
    assert data["modules"]["ai_engine"] == "ready"
    assert data["modules"]["tools_security"] == "ready"
    assert data["modules"]["notifications"] == "ready"
    assert data["modules"]["memory"] == "ready"
    assert data["modules"]["automation"] == "ready"
    assert data["modules"]["agents"] == "ready"
    assert data["modules"]["desktop"] == "ready"
