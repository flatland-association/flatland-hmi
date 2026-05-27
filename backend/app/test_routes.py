import tempfile
from uuid import UUID

from fastapi.testclient import TestClient

import app.routes
import pytest
from main import app as the_app

client = TestClient(the_app)


@pytest.fixture(scope="module", autouse=True)
def my_fixture():
    with tempfile.TemporaryDirectory() as tmpdirname:
        app.routes.DATA_DIR = tmpdirname
        yield


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
    ids = {p["id"] for p in body}
    assert ids == {"policy-0", "policy-1"}
    assert all("description" in p for p in body)


def test_get_envs():
    response = client.get("/envs")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    ids = {e["id"] for e in body}
    assert ids == {"generated-0", "generated-1"}
    assert all("description" in e for e in body)


def test_get_agents():
    response = client.get("/agents")
    assert response.status_code == 200
    body = response.json()
    print(body)


def test_get_agents():
    response = client.post("/step")
    assert response.status_code == 200
    body = response.json()
    print(body)


def test_post_get_trajectory():
    response = client.post("/trajectories", json={"policy_id": "policy-0", "env_id": "generated-0"})
    assert response.status_code == 200
    ep_id = response.json()
    assert isinstance(ep_id, str)
    UUID(ep_id)  # assert no fail
    assert ep_id in client.get("/trajectories").json()

    response = client.get("/trajectories")
    assert ep_id in response.json()


def test_get_trajectory_existing():
    ep_id = client.post("/trajectories", json={"policy_id": "policy-0", "env_id": "generated-0"}).json()
    response = client.get(f"/trajectories/{ep_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["ep_id"] == ep_id
    assert body["policy_id"] == "TODO"
    assert body["env_id"] == "TODO"


def test_get_trajectory_not_found():
    response = client.get("/trajectories/nonexistent-id")
    assert response.status_code == 404
