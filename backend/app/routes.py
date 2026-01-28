from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter
from fastapi import Request

from flatland.envs.rail_env import RailEnv
from flatland.trajectories.trajectories import Trajectory

router = APIRouter()

# TODO encapsulate in state
trajectory: Trajectory = None
initial_env: RailEnv = None
elapsed_steps = None
_info_dicts = defaultdict(dict)
_done_dicts = defaultdict(dict)
_positions_dicts = defaultdict(dict)


@router.get("/transitions")
def get_transitions():
    return initial_env.rail.grid.tolist()


# TODO add env_time as param
@router.get("/agents")
def get_map():
    global trajectory
    global elapsed_steps
    if elapsed_steps == 0:
        return [
            {
                "handle": agent.handle,
                "position": None,
                "direction": None,
                "moving": False,
                "speed_counter": agent.speed_counter,
                "target": (None if agent.target is None else tuple(int(c) for c in agent.target)),
                "malfunction": 0,
            }
            for agent in initial_env.agents
        ]

    return [
        {
            "handle": agent.handle,
            "position": _positions_dicts[elapsed_steps][agent.handle][0],
            "direction": _positions_dicts[elapsed_steps][agent.handle][1],
            "moving": _info_dicts[elapsed_steps][agent.handle]["state"] == 3,
            "speed_counter": _info_dicts[elapsed_steps][agent.handle]["speed"],
            "target": (None if agent.target is None else tuple(int(c) for c in agent.target)),
            "malfunction": _info_dicts[elapsed_steps][agent.handle]["malfunction"],
        }
        for agent in initial_env.agents
    ]


@router.post("/step")
def step_env(env_time: int):
    global trajectory
    global initial_env
    global elapsed_steps
    elapsed_steps = env_time
    d = {
        "info": _get_info_dict(env_time),
        "done": _get_done_dict(env_time),
        # "actions": {
        #     a: {"name": RailEnvActions.from_value(action).name, "value": RailEnvActions.from_value(action).value}
        #     for a, action in actions.items()
        # },
        "steps": env_time,
        "max_steps": initial_env._max_episode_steps,
    }
    env_time += 1
    return d


def _get_done_dict(env_time):
    global trajectory
    global initial_env
    global elapsed_steps
    # TODO improve Trajectory API to include env_time 0
    if env_time == 0:
        return {}
    return _done_dicts[env_time]


def _get_info_dict(env_time: int):
    global trajectory
    global initial_env
    global elapsed_steps
    # TODO improve Trajectory API to include env_time 0
    if env_time == 0:
        return {}
    return _info_dicts[env_time]


@router.post("/reset")
def reset_env(request: Request):
    global elapsed_steps
    global initial_env
    _reset_env()
    return {
        "info": _get_info_dict(elapsed_steps),
        "done": {"__all__": False},
        "steps": 0,
        "max_steps": initial_env._max_episode_steps
    }


def _reset_env():
    global trajectory
    global initial_env
    global elapsed_steps
    trajectory = Trajectory.load_existing(Path("/Users/che/workspaces/flatland-scenarios/scenario_generator/results_scenario_1_20260128_160703"),
                                          ep_id="scenario_1")
    for _, row in trajectory.trains_rewards_dones_infos.iterrows():
        _info_dicts[row["env_time"]][row["agent_id"]] = row["info"]
        _done_dicts[row["env_time"]][row["agent_id"]] = row["done"]
    for _, row in trajectory.trains_positions.iterrows():
        _positions_dicts[row["env_time"]][row["agent_id"]] = row["position"]
    initial_env = trajectory.load_env()
    elapsed_steps = 0
    return elapsed_steps


# https://download.eclipse.org/microprofile/microprofile-health-2.1/microprofile-health-spec.html#_constructing_healthcheckresponse_s
@router.get("/health/live")
def health_check():
    return {"status": "UP", "checks": []}


@router.get("/health/ready")
def health_check():
    return {"status": "UP", "checks": []}


_reset_env()
