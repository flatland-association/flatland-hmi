import asyncio
import json
from fractions import Fraction
from json import JSONEncoder
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi_lifecycle import deprecated
from pydantic import BaseModel

from app import trajectory_context
from app.env import reset_global_interactive_env, get_global_interactive_env, policy_map, env_map
from app.trajectory_context import TrajectoryContext
from flatland.envs.rail_env_action import RailEnvActions
from flatland.envs.step_utils.speed_counter import SpeedCounter


# https://www.getorchestra.io/guides/fastapi-custom-json-encoders-a-guide-to-converting-models-to-json
# https://github.com/fastapi/fastapi/discussions/8947
class CustomEncoder(JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Fraction):
            return {'__fraction__': True, 'as_str': str((obj.numerator, obj.denominator))}
        if isinstance(obj, SpeedCounter):
            return {'__speed_counter__': True, 'as_str': obj.__repr__()}
        return super().default(obj)


class CustomEncodedJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        return json.dumps(content, cls=CustomEncoder).encode('utf-8')


router = APIRouter()

global_interactive_env_lock = asyncio.Lock()


# https://download.eclipse.org/microprofile/microprofile-health-2.1/microprofile-health-spec.html#_constructing_healthcheckresponse_s
@router.get("/health/live")
def health_check_live():
    return {"status": "UP", "checks": []}


@router.get("/health/ready")
def health_check_ready():
    return {"status": "UP", "checks": []}


def _build_transitions_content(env) -> list:
    return env.rail.grid.tolist()


def _build_agents_content(env) -> list:
    return [
        {
            "handle": agent.handle,
            "position": (
                None if agent.position is None else tuple(int(c) for c in agent.position)
            ),
            "direction": agent.direction,
            "moving": agent.moving,
            "speed_counter": agent.speed_counter,
            "target": (
                None if agent.target is None else tuple(int(c) for c in agent.target)
            ),
            "malfunction": agent.malfunction_handler.malfunction_down_counter,
        }
        for agent in env.agents
    ]


@router.get("/transitions")
@deprecated({
    'replacement': 'GET /trajectories/{trajectoryId}/agents',
    'reason': 'Moving to ID-based API.'
})
async def get_transitions():
    async with global_interactive_env_lock:
        return _build_transitions_content(get_global_interactive_env().env)


@router.get("/agents")
@deprecated({
    'replacement': 'GET /trajectories/{trajectoryId}/agents',
    'reason': 'Moving to ID-based API.'
})
async def get_agents():
    async with global_interactive_env_lock:
        return CustomEncodedJSONResponse(
            content=_build_agents_content(get_global_interactive_env().env)
        )


@router.post("/step")
@deprecated({
    'replacement': 'GET /trajectories/{trajectoryId}/step',
    'reason': 'Moving to ID-based API.'
})
async def step_env(actions: dict = {}):
    async with global_interactive_env_lock:
        global_interactive_env = get_global_interactive_env()
        if global_interactive_env.done.get("__all__", False):
            raise HTTPException(status_code=412, detail=f"Environment already done.")
        _, _, done, info, actions = global_interactive_env.step(actions)
        return CustomEncodedJSONResponse(content={
            "info": info,
            "done": done,
            "actions": {
                a: {"name": RailEnvActions.from_value(action).name, "value": RailEnvActions.from_value(action).value}
                for a, action in actions.items()
            },
            "steps": global_interactive_env.env._elapsed_steps,
            "max_steps": global_interactive_env.env._max_episode_steps,
        })


@router.get("/policies")
async def get_policies():
    return [{"id": k, "description": v["description"]} for k, v in policy_map.items()]


@router.get("/envs")
async def get_envs():
    return [{"id": k, "description": v["description"]} for k, v in env_map.items()]


@router.post("/reset")
async def reset_env(request: Request):
    env_id = request.query_params.get("environment")
    policy_id = request.query_params.get("policy")
    if env_id not in env_map:
        raise HTTPException(status_code=400, detail=f"Unknown environment '{env_id}'. Valid: {list(env_map)}")
    if policy_id not in policy_map:
        raise HTTPException(status_code=400, detail=f"Unknown policy '{policy_id}'. Valid: {list(policy_map)}")
    async with global_interactive_env_lock:
        _, info = reset_global_interactive_env(env_id, policy_id)
        global_interactive_env = get_global_interactive_env()
        return CustomEncodedJSONResponse(content={
            "info": info,
            "done": {"__all__": False},
            "steps": global_interactive_env.env._elapsed_steps,
        })


@router.get("/trajectories")
async def get_trajectories():
    return [p.name for p in Path(trajectory_context.DATA_DIR).glob("*")]


class TrajectoryCreate(BaseModel):
    policy_id: str
    env_id: str


@router.post("/trajectories")
async def create_trajectory(body: TrajectoryCreate):
    policy_id = body.policy_id
    env_id = body.env_id
    ctx = TrajectoryContext.create(env_id, policy_id)
    return ctx.trajectory.ep_id


@router.get("/trajectories/{trajectory_id}")
async def get_trajectory(trajectory_id: str):
    ctx = TrajectoryContext.resolve(trajectory_id)

    return CustomEncodedJSONResponse(content=ctx.to_dict())


@router.post("/trajectories/{trajectory_id}/step")
async def trajectory_step(trajectory_id: str, body: dict = None):
    ctx = TrajectoryContext.resolve(trajectory_id)
    policy_id = None
    if body is not None:
        policy_id = body.get("policy_id", None)
    if policy_id is not None and policy_id not in policy_map:
        raise HTTPException(status_code=400, detail=f"Unknown policy '{policy_id}'. Valid: {list(policy_map)}")
    if ctx.policy_runner.env.dones.get("__all__", False):
        raise HTTPException(status_code=412, detail=f"Environment already done.")
    ctx.update_policy(policy_id)

    ctx.policy_runner.step(persist=False)
    if ctx.policy_runner.env.dones.get("__all__", False):
        ctx.policy_runner.trajectory.persist()
    return CustomEncodedJSONResponse(content=ctx.to_dict())


@router.post("/trajectories/{trajectory_id}/fork")
async def trajectory_fork(trajectory_id: str):
    ctx = TrajectoryContext.resolve(trajectory_id)
    if ctx.policy_runner is None:
        raise HTTPException(status_code=404, detail="Invalid policy ID")
    fork = ctx.fork()
    return CustomEncodedJSONResponse(content=fork.to_dict())


@router.get("/trajectories/{trajectory_id}/transitions")
async def get_trajectory_transitions(trajectory_id: str):
    ctx = TrajectoryContext.resolve(trajectory_id)
    env = ctx.get_env()
    return _build_transitions_content(env)


@router.get("/trajectories/{trajectory_id}/agents")
async def get_trajectory_agents(trajectory_id: str):
    ctx = TrajectoryContext.resolve(trajectory_id)
    env = ctx.get_env()
    return CustomEncodedJSONResponse(content=_build_agents_content(env))
