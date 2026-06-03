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
from fastapi_lifecycle import deprecated
from pydantic import BaseModel

from app.env import reset_global_interactive_env, get_global_interactive_env, policy_map, env_map
from app.policy_runner import policy_runner_map
from flatland.envs.rail_env_action import RailEnvActions
from flatland.envs.step_utils.speed_counter import SpeedCounter
from flatland.trajectories.policy_runner import PolicyRunner
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


def _get_or_load_trajectory_env(trajectory_id: str, p: Path):
    policy_runner = policy_runner_map.get(trajectory_id)
    if policy_runner is not None:
        return policy_runner.env
    t = Trajectory.load_existing(data_dir=p, ep_id=trajectory_id)
    return t.load_env(p, trajectory_id)


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
        reset_global_interactive_env(env_id, policy_id)
        global_interactive_env = get_global_interactive_env()
        _, info = global_interactive_env.reset()
        return CustomEncodedJSONResponse(content={
            "info": info,
            "done": {"__all__": False},
            "steps": global_interactive_env.env._elapsed_steps,
        })


def _resolve_trajectory_path(trajectory_id: str) -> Path:
    base = Path(DATA_DIR).resolve()
    p = (base / trajectory_id).resolve()
    if not str(p).startswith(str(base)):
        raise HTTPException(status_code=400, detail="Invalid trajectory ID")
    return p


@router.get("/trajectories")
async def get_trajectories():
    return [p.name for p in Path(DATA_DIR).glob("*")]


class TrajectoryCreate(BaseModel):
    policy_id: str
    env_id: str


@router.post("/trajectories")
async def post_trajectories(body: TrajectoryCreate):
    policy_id = body.policy_id
    env_id = body.env_id

    ep_id = str(uuid.uuid4())
    data_dir = Path(DATA_DIR) / ep_id
    data_dir.mkdir(exist_ok=True, parents=True)
    env = env_map.get(env_id)["factory"]()
    t = Trajectory.create_empty(data_dir, ep_id=ep_id, env=env)
    t_runner = PolicyRunner(
        policy=policy_map.get(policy_id)["factory"](),
        trajectory=t,
        env=env,
    )
    policy_runner_map[ep_id] = t_runner
    (data_dir / "meta.json").write_text(
        json.dumps({"policy_id": policy_id, "env_id": env_id})
    )
    return t.ep_id


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


@router.post("/trajectories/{trajectory_id}/step")
async def trajectory_step(trajectory_id: str):
    p = _resolve_trajectory_path(trajectory_id)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Trajectory not found")
    meta_path = p / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    policy_runner = policy_runner_map.get(trajectory_id, None)
    if policy_runner is None:
        t = Trajectory.load_existing(data_dir=p, ep_id=trajectory_id)
        policy_runner = PolicyRunner(
            policy=policy_map.get(meta.get("policy_id"))["factory"](),
            trajectory=t,
            env=t.load_env(p, trajectory_id),
        )
        policy_runner_map[trajectory_id] = policy_runner
    if policy_runner.env.dones.get("__all__", False):
        raise HTTPException(status_code=412, detail=f"Environment already done.")
    policy_runner.step(persist=False)
    if policy_runner.env.dones.get("__all__", False):
        policy_runner.trajectory.persist()

    return CustomEncodedJSONResponse(content={
        "ep_id": trajectory_id,
        "policy_id": meta.get("policy_id"),
        "env_id": meta.get("env_id"),
        "elapsed_steps": policy_runner.env._elapsed_steps,
        "done": policy_runner.env.dones.get("__all__", False),
    })


@router.get("/trajectories/{trajectory_id}/transitions")
async def get_trajectory_transitions(trajectory_id: str):
    p = _resolve_trajectory_path(trajectory_id)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Trajectory not found")
    env = _get_or_load_trajectory_env(trajectory_id, p)
    return _build_transitions_content(env)


@router.get("/trajectories/{trajectory_id}/agents")
async def get_trajectory_agents(trajectory_id: str):
    p = _resolve_trajectory_path(trajectory_id)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Trajectory not found")
    env = _get_or_load_trajectory_env(trajectory_id, p)
    return CustomEncodedJSONResponse(content=_build_agents_content(env))
