import tempfile
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app import trajectory_context
from main import app as the_app

client = TestClient(the_app)


@pytest.fixture(scope="module", autouse=True)
def my_fixture():
    with tempfile.TemporaryDirectory() as tmpdirname:
        trajectory_context.DATA_DIR = tmpdirname
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
    trajectory_context.trajectory_context_map.pop(ep_id)
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
    trajectory_context.trajectory_context_map.pop(ep_id)
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
    trajectory_context.trajectory_context_map.pop(ep_id)
    response = client.get(f"/trajectories/{ep_id}/agents")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) > 0
    required_keys = {"handle", "position", "direction", "moving", "speed_counter", "target", "malfunction"}
    assert all(required_keys <= set(agent.keys()) for agent in body)


def test_get_trajectory_agent_transitions():
    ep_id = client.post("/trajectories", json={"policy_id": "policy-0", "env_id": "generated-0"}).json()
    response = client.get(f"/trajectories/{ep_id}/zwl/0")
    assert response.status_code == 200
    body = response.json()
    required_keys = {"grid", "mapping"}
    assert required_keys <= set(body.keys())


def test_get_trajectory_agent_transitions_invalid_agent():
    ep_id = client.post("/trajectories", json={"policy_id": "policy-0", "env_id": "generated-0"}).json()
    response = client.get(f"/trajectories/{ep_id}/zwl/9999")
    assert response.status_code == 404


def test_get_trajectory_agent_transitions_not_found():
    response = client.get("/trajectories/nonexistent-id/zwl/0")
    assert response.status_code == 404


def test_get_trajectory_agent_transitions_path_traversal():
    response = client.get("/trajectories/../../etc/passwd/zwl/0")
    assert response.status_code in (400, 404)


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


def test_get_trajectory_links():
    ep_id = client.post("/trajectories", json={"policy_id": "policy-0", "env_id": "generated-0"}).json()
    response = client.get(f"/trajectories/{ep_id}/links")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert {"cityFrom",
            "cityTo",
            "label",
            "startStationName",
            "endStationName", } <= body[0].keys()


def test_get_trajectory_lines_invalid_agent():
    ep_id = client.post("/trajectories", json={"policy_id": "policy-0", "env_id": "generated-0"}).json()
    response = client.get(f"/trajectories/{ep_id}/lines/9999")
    assert response.status_code == 404


def test_get_trajectory_lines_not_found():
    response = client.get("/trajectories/nonexistent-id/lines/0")
    assert response.status_code == 404


def test_get_trajectory_lines_path_traversal():
    response = client.get("/trajectories/../../etc/passwd/lines/0")
    assert response.status_code in (400, 404)


def test_get_trajectory_stations():
    ep_id = client.post("/trajectories", json={"policy_id": "policy-0", "env_id": "generated-0"}).json()
    response = client.get(f"/trajectories/{ep_id}/stations")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, dict)
    assert {"station_edges", "station_gates", "links"} <= body.keys()
    station_edges = body["station_edges"]
    assert isinstance(station_edges, dict)
    assert len(station_edges) > 0
    assert all(
        isinstance(cells, list) and all(isinstance(c, list) and len(c) == 2 for c in cells)
        for cells in station_edges.values()
    )


def test_get_trajectory_stations_not_found():
    response = client.get("/trajectories/nonexistent-id/stations")
    assert response.status_code == 404


def test_get_trajectory_stations_path_traversal():
    response = client.get("/trajectories/../../etc/passwd/stations")
    assert response.status_code in (400, 404)
