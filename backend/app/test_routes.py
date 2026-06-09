import tempfile
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

import app.routes
from app.policy_runner import policy_runner_map
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


def test_post_step():
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
    assert body["policy_id"] == "policy-0"
    assert body["env_id"] == "generated-0"


def test_get_trajectory_path_traversal():
    response = client.get("/trajectories/../../etc/passwd")
    assert response.status_code in (400, 404)


def test_reset_invalid_params():
    response = client.post("/reset")
    assert response.status_code == 400

    response = client.post("/reset?environment=bad&policy=bad")
    assert response.status_code == 400


def test_get_trajectory_not_found():
    response = client.get("/trajectories/nonexistent-id")
    assert response.status_code == 404


def test_post_trajectory_step():
    ep_id = client.post("/trajectories", json={"policy_id": "policy-0", "env_id": "generated-0"}).json()
    response = client.post(f"/trajectories/{ep_id}/step")
    assert response.status_code == 200
    body = response.json()
    assert body["ep_id"] == ep_id
    assert body["policy_id"] == "policy-0"
    assert body["env_id"] == "generated-0"
    elapsed_steps_ = body["elapsed_steps"]
    assert isinstance(elapsed_steps_, int) and elapsed_steps_ >= 1
    response = client.post(f"/trajectories/{ep_id}/step")
    assert response.json()["elapsed_steps"] == elapsed_steps_ + 1


def test_post_trajectory_step_policy_runner_not_in_map():
    ep_id = client.post("/trajectories", json={"policy_id": "policy-0", "env_id": "generated-0"}).json()
    policy_runner_map.pop(ep_id)
    response = client.post(f"/trajectories/{ep_id}/step")
    assert response.status_code == 200
    body = response.json()
    assert body["ep_id"] == ep_id
    assert body["policy_id"] == "policy-0"
    assert body["env_id"] == "generated-0"
    elapsed_steps_ = body["elapsed_steps"]
    assert isinstance(elapsed_steps_, int) and elapsed_steps_ >= 1
    response = client.post(f"/trajectories/{ep_id}/step")
    assert response.json()["elapsed_steps"] == elapsed_steps_ + 1


def test_post_trajectory_step_with_policy():
    ep_id = client.post("/trajectories", json={"policy_id": "policy-0", "env_id": "generated-0"}).json()
    policy_runner_map.pop(ep_id)
    response = client.post(f"/trajectories/{ep_id}/step", json={"policy_id": "policy-1"})
    assert response.status_code == 200
    body = response.json()
    assert body["ep_id"] == ep_id
    assert isinstance(body["elapsed_steps"], int) and body["elapsed_steps"] >= 1
    assert body["policy_id"] == "policy-1"


def test_post_trajectory_step_invalid_policy():
    ep_id = client.post("/trajectories", json={"policy_id": "policy-0", "env_id": "generated-0"}).json()
    response = client.post(f"/trajectories/{ep_id}/step", json={"policy_id": "nonexistent"})
    assert response.status_code == 400


def test_post_trajectory_step_not_found():
    response = client.post("/trajectories/nonexistent-id/step")
    assert response.status_code == 404


def test_post_trajectory_fork():
    ep_id = client.post("/trajectories", json={"policy_id": "policy-0", "env_id": "generated-0"}).json()
    client.post(f"/trajectories/{ep_id}/step")
    response = client.post(f"/trajectories/{ep_id}/fork")
    assert response.status_code == 200
    body = response.json()
    fork_id = body["ep_id"]
    assert fork_id != ep_id
    UUID(fork_id)
    assert body["policy_id"] == "policy-0"
    assert body["env_id"] == "generated-0"
    assert isinstance(body["elapsed_steps"], int)
    assert fork_id in client.get("/trajectories").json()


def test_post_trajectory_fork_not_found():
    response = client.post("/trajectories/nonexistent-id/fork")
    assert response.status_code == 404


def test_post_trajectory_fork_path_traversal():
    response = client.post("/trajectories/../../etc/passwd/fork")
    assert response.status_code in (400, 404)


def test_get_trajectory_transitions():
    ep_id = client.post("/trajectories", json={"policy_id": "policy-0", "env_id": "generated-0"}).json()
    response = client.get(f"/trajectories/{ep_id}/transitions")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) > 0


def test_get_trajectory_agents():
    ep_id = client.post("/trajectories", json={"policy_id": "policy-0", "env_id": "generated-0"}).json()
    response = client.get(f"/trajectories/{ep_id}/agents")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) > 0
    required_keys = {"handle", "position", "direction", "moving", "speed_counter", "target", "malfunction"}
    assert all(required_keys <= set(agent.keys()) for agent in body)


def test_get_trajectory_agents_runner_not_in_map():
    ep_id = client.post("/trajectories", json={"policy_id": "policy-0", "env_id": "generated-0"}).json()
    client.post(f"/trajectories/{ep_id}/step")
    policy_runner_map.pop(ep_id)
    response = client.get(f"/trajectories/{ep_id}/agents")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) > 0
    required_keys = {"handle", "position", "direction", "moving", "speed_counter", "target", "malfunction"}
    assert all(required_keys <= set(agent.keys()) for agent in body)


def test_get_trajectory_transitions_not_found():
    response = client.get("/trajectories/nonexistent-id/transitions")
    assert response.status_code == 404


def test_get_trajectory_agents_not_found():
    response = client.get("/trajectories/nonexistent-id/agents")
    assert response.status_code == 404


def test_get_trajectory_transitions_path_traversal():
    response = client.get("/trajectories/../../etc/passwd/transitions")
    assert response.status_code in (400, 404)


def test_get_trajectory_agents_path_traversal():
    response = client.get("/trajectories/../../etc/passwd/agents")
    assert response.status_code in (400, 404)
