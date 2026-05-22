import asyncio
import json
from fractions import Fraction
from json import JSONEncoder
from typing import Any

from fastapi import APIRouter
from fastapi import Request
from fastapi.responses import JSONResponse

from app.env import reset_global_interactive_env, get_global_interactive_env, policy_map, env_map, trajectory_map
from flatland.envs.rail_env_action import RailEnvActions
from flatland.envs.step_utils.speed_counter import SpeedCounter


# https://www.getorchestra.io/guides/fastapi-custom-json-encoders-a-guide-to-converting-models-to-json
# https://github.com/fastapi/fastapi/discussions/8947
class FractionEncoder(JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Fraction):
            return {'__fraction__': True, 'as_str': str((obj.numerator, obj.denominator))}
        if isinstance(obj, SpeedCounter):
            return {'__speed_counter__': True, 'as_str': obj.__repr__()}
        return super().default(obj)


class FractionJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        return json.dumps(content, cls=FractionEncoder).encode('utf-8')


router = APIRouter()

global_interactive_env_lock = asyncio.Lock()

@router.get("/transitions")
async def get_transitions():
    async with global_interactive_env_lock:
        global_interactive_env = get_global_interactive_env()
        return global_interactive_env.env.rail.grid.tolist()


@router.get("/agents")
async def get_agents():
    async with global_interactive_env_lock:
        global_interactive_env = get_global_interactive_env()
        return FractionJSONResponse(content=[
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
            for agent in global_interactive_env.env.agents
        ])


@router.get("/policies")
async def get_policies():
    return list(policy_map.keys())


@router.get("/envs")
async def get_envs():
    return list(env_map.keys())


@router.get("/trajectories")
async def get_trajectories():
    return list(trajectory_map.keys())


@router.post("/step")
async def step_env(actions: dict = {}):
    async with global_interactive_env_lock:
        global_interactive_env = get_global_interactive_env()
        _, _, done, info, actions = global_interactive_env.step(actions)
        return FractionJSONResponse(content={
            "info": info,
            "done": done,
            "actions": {
                a: {"name": RailEnvActions.from_value(action).name, "value": RailEnvActions.from_value(action).value}
                for a, action in actions.items()
            },
            "steps": global_interactive_env.env._elapsed_steps,
            "max_steps": global_interactive_env.env._max_episode_steps,
        })


@router.post("/reset")
async def reset_env(request: Request):
    async with global_interactive_env_lock:
        reset_global_interactive_env(request.query_params.get("environment"), request.query_params.get("policy"))
        global_interactive_env = get_global_interactive_env()
        _, info = global_interactive_env.reset()
        return FractionJSONResponse(content={
            "info": info,
            "done": {"__all__": False},
            "steps": global_interactive_env.env._elapsed_steps,
        })


# https://download.eclipse.org/microprofile/microprofile-health-2.1/microprofile-health-spec.html#_constructing_healthcheckresponse_s
@router.get("/health/live")
def health_check():
    return {"status": "UP", "checks": []}


@router.get("/health/ready")
def health_check():
    return {"status": "UP", "checks": []}
