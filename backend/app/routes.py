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


@router.get("/transitions")
def get_transitions():
    return initial_env.rail.grid.tolist()


@router.get("/agents")
def get_map():
    global trajectory
    global elapsed_steps
    curr_env = trajectory.load_env(start_step=elapsed_steps)
    return [
        {
            "handle": agent.handle,
            "position": (
                None
                if agent.position is None
                else tuple(int(c) for c in agent.position)
            ),
            "direction": agent.direction,
            "moving": agent.moving,
            "speed_counter": agent.speed_counter,
            "target": (
                None if agent.target is None else tuple(int(c) for c in agent.target)
            ),
            "malfunction": agent.malfunction_handler.malfunction_down_counter,
        }
        for agent in curr_env.agents
    ]


@router.post("/step")
def step_env(env_time:int):
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
    return {agent_id: bool(trajectory.trains_rewards_dones_infos_lookup(env_time=env_time, agent_id=agent_id)[1]) for agent_id in
            initial_env.get_agent_handles()}


def _get_info_dict(env_time: int):
    global trajectory
    global initial_env
    global elapsed_steps
    # TODO improve Trajectory API to include env_time 0
    if env_time == 0:
        return {}
    return {agent_id: trajectory.trains_rewards_dones_infos_lookup(env_time=env_time, agent_id=agent_id)[2] for agent_id in initial_env.get_agent_handles()}


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
    trajectory = Trajectory.load_existing(Path("/Users/che/workspaces/flatland-scenarios/scenario_generator/results_scenario_1_20260128_121434"), ep_id="scenario_1")
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
