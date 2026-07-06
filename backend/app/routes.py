import asyncio
import json
from fractions import Fraction
from json import JSONEncoder
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from attr import asdict
from fastapi import APIRouter, HTTPException
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi_lifecycle import deprecated
from pydantic import BaseModel

from app import trajectory_context
from app.env import reset_global_interactive_env, get_global_interactive_env, policy_map, env_map
from app.link_map import extract_link_map
from app.trajectory_context import TrajectoryContext
from flatland.envs.rail_env_action import RailEnvActions
from flatland.envs.rail_trainrun_data_structures import Waypoint
from flatland.envs.stations_links import Gate, Link, Fibre, Pin, Station, StationsLinks, StoppingPoint
from flatland.envs.step_utils.speed_counter import SpeedCounter


# https://www.getorchestra.io/guides/fastapi-custom-json-encoders-a-guide-to-converting-models-to-json
# https://github.com/fastapi/fastapi/discussions/8947
class CustomEncoder(JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Fraction):
            return {'__fraction__': True, 'as_str': str((obj.numerator, obj.denominator))}
        if isinstance(obj, SpeedCounter):
            return {'__speed_counter__': True, 'as_str': obj.__repr__()}
        if isinstance(obj, Waypoint):
            return asdict(obj)
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
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


def build_stations_and_links_payload(stations_links: StationsLinks) -> dict:
    print(stations_links)
    station_edges: Dict[str, Any] = {}
    station_stopping_points: Dict[str, List[dict]] = {}
    station_gates: Dict[str, Dict[str, dict]] = {}

    station_name: str
    station: Station
    for station_name, station in stations_links.stations.items():
        station_edges[station_name] = station.edges

        stp: StoppingPoint
        station_stopping_points[station_name] = [
            {"node": stp.node, "trackName": stp.name}
            for stp in station.stopping_points
        ]

        gate_key: str
        gate: Gate
        station_gates[station_name] = {}
        for gate_key, gate in station.gates.items():
            pin_key: int
            p: Pin
            station_gates[station_name][gate_key] = {
                "name": gate.name,
                "pins": {pin_key: {"name": p.name, "node": p.node} for pin_key, p in gate.pins.items()},
            }

    links_payload: List[dict] = []
    link: Link
    for link in stations_links.links:
        fibre: Fibre
        links_payload.append({
            "fromPin": link.from_pin,
            "toPin": link.to_pin,
            "fibres": [{"cells": fibre.edges} for fibre in link.fibres],
        })

    return {
        "stationEdges": station_edges,
        "stationStoppingPoints": station_stopping_points,
        "stationGates": station_gates,
        "links": links_payload,
    }


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
async def step_env(actions: Optional[dict] = None):
    if actions is None:
        actions = {}
    async with global_interactive_env_lock:
        global_interactive_env = get_global_interactive_env()
        if global_interactive_env.done.get("__all__", False):
            raise HTTPException(status_code=412, detail="Environment already done.")
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
@deprecated({
    'replacement': 'POST /trajectories',
    'reason': 'Moving to ID-based API.'
})
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
        raise HTTPException(status_code=412, detail="Environment already done.")
    ctx.update_policy(policy_id)

    ctx.policy_runner.step(persist=False)
    if ctx.policy_runner.env.dones.get("__all__", False):
        ctx.policy_runner.trajectory.persist()
    return CustomEncodedJSONResponse(content=ctx.to_dict())


@router.post("/trajectories/{trajectory_id}/fork")
async def trajectory_fork(trajectory_id: str):
    ctx = TrajectoryContext.resolve(trajectory_id)
    fork = ctx.fork()
    return CustomEncodedJSONResponse(content=fork.to_dict())


@router.get("/trajectories/{trajectory_id}/transitions")
async def get_trajectory_transitions(trajectory_id: str):
    ctx = TrajectoryContext.resolve(trajectory_id)
    env = ctx.get_env()
    return _build_transitions_content(env)


@router.get("/trajectories/{trajectory_id}/link/{link_id}/map")
async def get_trajectory_agent_transitions(trajectory_id: str, link_id: int):
    ctx = TrajectoryContext.resolve(trajectory_id)
    env = ctx.get_env()
    links = env.stations_links.links
    if link_id < 0 or link_id >= len(links):
        raise HTTPException(status_code=404, detail=f"Link {link_id} not found.")

    link = links[link_id]
    if not link.fibres:
        raise HTTPException(status_code=422, detail=f"Link {link_id} has no fibres.")
    fibre = link.fibres[0]
    content = extract_link_map(env.stations_links, link, fibre, env.rail)
    return CustomEncodedJSONResponse(content=content)


@router.get("/trajectories/{trajectory_id}/stations")
async def get_trajectory_stations(trajectory_id: str):
    ctx = TrajectoryContext.resolve(trajectory_id)
    env = ctx.get_env()
    return CustomEncodedJSONResponse(content=build_stations_and_links_payload(env.stations_links))


@router.get("/trajectories/{trajectory_id}/agents")
async def get_trajectory_agents(trajectory_id: str):
    ctx = TrajectoryContext.resolve(trajectory_id)
    env = ctx.get_env()
    return CustomEncodedJSONResponse(content=_build_agents_content(env))


def _enrich_link(link: dict, link_id: int) -> dict:
    from_station, from_dir, _ = link["fromPin"].split(".")
    to_station, to_dir, _ = link["toPin"].split(".")
    return {
        "cityFrom": from_station,
        "cityTo": to_station,
        "fromGate": f"{from_station}.{from_dir}",
        "toGate": f"{to_station}.{to_dir}",
        "label": f"Link {link_id} ({link['fromPin']} → {link['toPin']})",
        "startStationName": f"Station {from_station}",
        "endStationName": f"Station {to_station}",
    }


@router.get("/trajectories/{trajectory_id}/links")
async def get_trajectory_links(trajectory_id: str):
    ctx = TrajectoryContext.resolve(trajectory_id)
    env = ctx.get_env()
    stations_links = build_stations_and_links_payload(env.stations_links)
    links = stations_links["links"]
    return CustomEncodedJSONResponse(content=[
        _enrich_link(link, i) for i, link in enumerate(links)
    ])


@router.get("/trajectories/{trajectory_id}/links/{link_id}")
async def get_trajectory_lines(trajectory_id: str, link_id: int):
    ctx = TrajectoryContext.resolve(trajectory_id)
    env = ctx.get_env()
    stations_links = build_stations_and_links_payload(env.stations_links)
    links = stations_links["links"]
    if link_id < 0 or link_id >= len(links):
        raise HTTPException(status_code=404, detail=f"Link {link_id} not found.")
    return CustomEncodedJSONResponse(content=_enrich_link(links[link_id], link_id))
