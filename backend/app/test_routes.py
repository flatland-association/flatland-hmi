from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_live():
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "UP", "checks": []}


def test_health_ready():
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "UP", "checks": []}


def test_get_policies():
    response = client.get("/policies")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert set(body) == {"policy-0", "policy-1"}
