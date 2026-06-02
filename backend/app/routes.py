import asyncio
import json
import os
import uuid
from fractions import Fraction
from json import JSONEncoder
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.env import reset_global_interactive_env, get_global_interactive_env, policy_map, env_map
from flatland.envs.rail_env_action import RailEnvActions
from flatland.envs.step_utils.speed_counter import SpeedCounter
from flatland.trajectories.trajectories import Trajectory


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

DATA_DIR = os.getenv("HMI_DATA_DIR", "./hmi_data_dir")


# https://download.eclipse.org/microprofile/microprofile-health-2.1/microprofile-health-spec.html#_constructing_healthcheckresponse_s
@router.get("/health/live")
def health_check_live():
    return {"status": "UP", "checks": []}


@router.get("/health/ready")
def health_check_ready():
    return {"status": "UP", "checks": []}


@router.get("/transitions")
async def get_transitions():
    async with global_interactive_env_lock:
        global_interactive_env = get_global_interactive_env()
        return global_interactive_env.env.rail.grid.tolist()


@router.get("/agents")
async def get_agents():
    async with global_interactive_env_lock:
        global_interactive_env = get_global_interactive_env()
        return CustomEncodedJSONResponse(content=[
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
    return [{"id": k, "description": v["description"]} for k, v in policy_map.items()]


@router.get("/envs")
async def get_envs():
    return [{"id": k, "description": v["description"]} for k, v in env_map.items()]


@router.post("/step")
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


@router.post("/reset")
async def reset_env(request: Request):
    env_id = request.query_params.get("environment")
    policy_id = request.query_params.get("policy")
    if env_id not in env_map:
        raise HTTPException(status_code=400, detail=f"Unknown environment '{env_id}'. Valid: {list(env_map)}")
    if policy_id not in policy_map:
        raise HTTPException(status_code=400, detail=f"Unknown policy '{policy_id}'. Valid: {list(policy_map)}")
    async with global_interactive_env_lock:
        reset_global_interactive_env(env_id, policy_id)
        global_interactive_env = get_global_interactive_env()
        _, info = global_interactive_env.reset()
        return CustomEncodedJSONResponse(content={
            "info": info,
            "done": {"__all__": False},
            "steps": global_interactive_env.env._elapsed_steps,
        })


@router.get("/trajectories")
async def get_trajectories():
    return [p.name for p in Path(DATA_DIR).glob("*")]


class TrajectoryCreate(BaseModel):
    policy_id: str
    env_id: str


@router.post("/trajectories")
async def post_trajectories(body: TrajectoryCreate):
    ep_id = str(uuid.uuid4())
    data_dir = Path(DATA_DIR) / ep_id
    data_dir.mkdir(exist_ok=True, parents=True)
    t = Trajectory.create_empty(data_dir, ep_id=ep_id)
    (data_dir / "meta.json").write_text(
        json.dumps({"policy_id": body.policy_id, "env_id": body.env_id})
    )
    return t.ep_id


def _resolve_trajectory_path(trajectory_id: str) -> Path:
    base = Path(DATA_DIR).resolve()
    p = (base / trajectory_id).resolve()
    if not str(p).startswith(str(base)):
        raise HTTPException(status_code=400, detail="Invalid trajectory ID")
    return p


@router.get("/trajectories/{trajectory_id}")
async def get_trajectory(trajectory_id: str):
    p = _resolve_trajectory_path(trajectory_id)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Trajectory not found")
    meta_path = p / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    Trajectory.load_existing(Path(DATA_DIR), trajectory_id)
    return CustomEncodedJSONResponse(content={
        "ep_id": trajectory_id,
        "policy_id": meta.get("policy_id"),
        "env_id": meta.get("env_id"),
    })
