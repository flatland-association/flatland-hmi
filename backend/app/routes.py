from fastapi import APIRouter
from fastapi import Request
from flatland.envs.rail_env_action import RailEnvActions

from app.env import interactive_env, reset_global_interactive_env

router = APIRouter()


@router.get("/transitions")
def get_transitions():
    return interactive_env.env.rail.grid.tolist()


@router.get("/agents")
def get_map():
    return [
        {
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
        for agent in interactive_env.env.agents
    ]


@router.post("/step")
def step_env(actions: dict = {}):
    _, _, done, info, actions = interactive_env.step(actions)
    return {
        "info": info,
        "done": done,
        "actions": {
            a: {"name": RailEnvActions.from_value(action).name, "value": RailEnvActions.from_value(action).value}
            for a, action in actions.items()
        },
        "steps": interactive_env.env._elapsed_steps,
        "max_steps": interactive_env.env._max_episode_steps,
    }


@router.post("/reset")
def reset_env(request: Request):
    global interactive_env
    interactive_env = reset_global_interactive_env(request.query_params.get("environment"), request.query_params.get("policy"))
    _, info = interactive_env.reset()
    return {
        "info": info,
        "done": {"__all__": False},
        "steps": interactive_env.env._elapsed_steps,
    }


# https://download.eclipse.org/microprofile/microprofile-health-2.1/microprofile-health-spec.html#_constructing_healthcheckresponse_s
@router.get("/health/live")
def health_check():
    return {"status": "UP", "checks": []}


@router.get("/health/ready")
def health_check():
    return {"status": "UP", "checks": []}
