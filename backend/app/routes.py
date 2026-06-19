import asyncio
import json
from fractions import Fraction
from json import JSONEncoder
from pathlib import Path
from typing import Any, Optional

import numpy as np
from attr import asdict
from fastapi import APIRouter, HTTPException
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi_lifecycle import deprecated
from numpy import dtype, floating, ndarray
from numpy._typing import _64Bit
from pydantic import BaseModel

from app import trajectory_context
from app.env import reset_global_interactive_env, get_global_interactive_env, policy_map, env_map
from app.trajectory_context import TrajectoryContext
from flatland.core.transition_map import GridTransitionMap
from flatland.envs.grid.rail_env_grid import RailEnvTransitions, RailEnvTransitionsEnum
from flatland.envs.grid4_generators_utils import connect_rail_in_grid_map
from flatland.envs.rail_env import RailEnv
from flatland.envs.rail_env_action import RailEnvActions
from flatland.envs.rail_trainrun_data_structures import Waypoint
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


def _build_stations_and_links_payload(env) -> dict:
    station_edges = {i: station["edges"] for i, station in env.stations_links["stations"].items()}
    station_stopping_points = {i: [{"node": stp["node"], "trackNumber": stp["track_number"], "trackName": stp["name"]} for stp in v["stopping_points"]] for
                               i, v in env.stations_links["stations"].items()}

    station_gates = {i: [{"name": gate["name"],
                          "pins": {k: {"name": v["name"], "node": v["node"]} for k, v in gate["pins"].items()}} for _, gate in v["gates"].items()] for i, v
                     in env.stations_links["stations"].items()}
    return {
        "station_edges": station_edges,
        "station_stopping_points": station_stopping_points,
        "station_gates": station_gates,

        "links": [{
            "fromStation": link["from_station"],
            "fromGate": link["from_gate"],
            "fromFacing": link["from_facing"],
            "toStation": link["to_station"],
            "toGate": link["to_gate"],
            "toFacing": link["to_facing"],
            "fibres": [{
                "fromPin": fibre["from_pin"],
                "toPin": fibre["to_pin"],
                "cells": fibre["edges"],
            } for fibre in link["fibres"]],
        } for link in env.stations_links["links"]],
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


@router.get("/trajectories/{trajectory_id}/zwl/{line_id}")
async def get_trajectory_agent_transitions(trajectory_id: str, line_id: int):
    ctx = TrajectoryContext.resolve(trajectory_id)
    env = ctx.get_env()
    stations_lines = _build_stations_and_links_payload(env)
    fibres_flat = [(link, fibre) for link in stations_lines["links"] for fibre in link["fibres"]]
    if line_id < 0 or line_id >= len(fibres_flat):
        raise HTTPException(status_code=404, detail=f"Line {line_id} not found.")

    current_link, fibre = fibres_flat[line_id]
    print("fibre")
    print(fibre)
    start = tuple(fibre["cells"][0])
    end = tuple(fibre["cells"][-1])
    from_station = current_link["fromStation"]
    from_facing = _DIRECTION_CHARS[current_link["fromFacing"]]
    to_station = current_link["toStation"]
    to_facing = _DIRECTION_CHARS[current_link["toFacing"]]

    grid = np.zeros(shape=(env.rail.grid.shape[0], env.rail.grid.shape[1] + 50), dtype=int)
    city_1_bb, city_cells_bbox, mapping1 = _extract_city_rotated(from_station, from_facing, env, stations_lines, 1)
    city_2_bb, city_cells_bbox, mapping2 = _extract_city_rotated(to_station, to_facing, env, stations_lines, 3)

    start_y = mapping1[start][0]
    end_y = mapping2[end][0]
    straight_y = max(start_y, end_y)
    x_offset_1 = 0
    y_offset_1 = 0
    if start_y < straight_y:
        y_offset_1 = straight_y - start_y
    grid[y_offset_1:city_1_bb.shape[0] + y_offset_1, :city_1_bb.shape[1]] = city_1_bb
    mapping1 = {k: (r + y_offset_1, c + x_offset_1) for k, (r, c) in mapping1.items()}

    y_offset_2 = 00
    # first and last cell of line in stations bb
    x_offset_2 = city_1_bb.shape[1] + len(fibre["cells"]) - 2
    if end_y < straight_y:
        y_offset_2 = straight_y - end_y
    grid[y_offset_2:city_2_bb.shape[0] + y_offset_2, x_offset_2:city_2_bb.shape[1] + x_offset_2] = city_2_bb

    grid = grid[:max(city_1_bb.shape[0] + y_offset_1, city_2_bb.shape[0] + y_offset_2), :x_offset_2 + city_2_bb.shape[1]]

    mapping2 = {k: (r + y_offset_2, c + x_offset_2) for k, (r, c) in mapping2.items()}

    mapping = {**mapping1, **mapping2}
    print(f"mapping {mapping}")

    grid_map = GridTransitionMap(height=grid.shape[0], width=grid.shape[1], transitions=RailEnvTransitions(), grid=grid)
    path = connect_rail_in_grid_map(
        grid_map=grid_map,
        rail_trans=RailEnvTransitions(),
        start=mapping[start],
        end=mapping[end],
    )
    print("path")
    print(path)
    assert path[0] == mapping[start]
    assert path[-1] == mapping[end]
    assert len(fibre["cells"]) == len(path)
    print(fibre["cells"])
    print(path)
    for i, cell in enumerate(path):
        mapping[fibre["cells"][i]] = cell

    # TODO we must find all paths of the link

    # TODO find all forks/joins leaving/joining our link
    covered = set()

    for other_line_id, (other_link, other_fibre) in enumerate(fibres_flat):
        if other_line_id == line_id:
            continue

        if current_link["fromGate"] == other_link["fromGate"] and current_link["toGate"] == other_link["toGate"]:
            print(f"testing {other_line_id} {other_fibre}")
            print(fibre["cells"])
            print(other_fibre["cells"])
            start_path = other_fibre["cells"][0]

            for c, c_ in zip(other_fibre["cells"], other_fibre["cells"][1:]):
                # end overlap -> keep track of start_path and do later
                if c in fibre["cells"] and c_ not in fibre["cells"]:
                    start_path = c

                # start of overlap -> path from start_path
                if c not in fibre["cells"] and c_ in fibre["cells"]:
                    # path joining into line
                    # TODO must consider direction -> otherwise not connected correctly (switche might be against the line's direction)
                    print(f"path joining into line {c_} <- {start_path}")
                    covered.add(c_)
                    connect_rail_in_grid_map(
                        grid_map=grid_map,
                        rail_trans=RailEnvTransitions(),
                        start=mapping[start_path],
                        end=mapping[c_],
                    )
                    start_path = None
                    # TODO add mapping
            # path forking from line but not joining again
            if start_path is not None:
                print(f"path forking from line {start_path} -> {other_fibre['cells'][-1]}")
                covered.add(start_path)
                connect_rail_in_grid_map(
                    grid_map=grid_map,
                    rail_trans=RailEnvTransitions(),
                    start=mapping[start_path],
                    end=mapping[other_fibre["cells"][-1]],
                )
                # TODO add mapping
    for cell in fibre["cells"]:
        if not RailEnvTransitionsEnum.is_one_one(env.rail.grid[cell[0]][cell[1]]) and not cell in covered:

            zwl_cell = mapping[cell]
            print(f"Found uncovered switch in line {cell} -> {zwl_cell}")
            if grid[zwl_cell[0] + 1][zwl_cell[1]] == 0:
                grid[zwl_cell[0] + 1][zwl_cell[1]] = RailEnvTransitionsEnum.vertical_straight.value
            elif grid[zwl_cell[0] - 1][zwl_cell[1]] == 0:
                grid[zwl_cell[0] - 1][zwl_cell[1]] = RailEnvTransitionsEnum.vertical_straight.value
            else:
                raise Exception("Could not")

    return CustomEncodedJSONResponse(content={
        # ZWL grid
        "grid": grid,
        # env -> ZWL coordindates
        "mapping": [[[r, c], list(v)] for (r, c), v in mapping.items()],
        "city_cells_bbox": city_cells_bbox,
    })


def _extract_city_rotated(city: int, city_orientation, env: RailEnv | None, stations_lines: dict, target_facing=1) -> tuple[
    ndarray[Any, dtype[floating[_64Bit]]], dict[str, Any]]:
    num_rot = target_facing - city_orientation
    num_rot %= 4
    print(f"city_orientation={city_orientation}, target_facing={target_facing}, num_rot={num_rot}")
    print(f"rotate={num_rot}")

    all_city_cells = [cell for cell in stations_lines["station_edges"][city]]
    city_cells_bbox = {
        "min_row": min(cell[0] for cell in all_city_cells),
        "max_row": max(cell[0] for cell in all_city_cells),
        "min_col": min(cell[1] for cell in all_city_cells),
        "max_col": max(cell[1] for cell in all_city_cells),
    }
    print("city_cells_bbox")
    print(city_cells_bbox)

    city_bb = env.rail.grid[city_cells_bbox["min_row"]:city_cells_bbox["max_row"] + 1, city_cells_bbox["min_col"]:city_cells_bbox["max_col"] + 1].copy()
    # print("city_bb")
    # print(city_bb)
    height, width = city_bb.shape

    city_bb = np.rot90(city_bb, -1 * num_rot)
    # print("city_bb after rotation")
    # print(city_bb)

    for r in range(city_bb.shape[0]):
        for c in range(city_bb.shape[1]):
            city_bb[r, c] = RailEnvTransitions().rotate_transition(city_bb[r, c], rotation=90 * num_rot)

    def rotate(r, c, max_r):
        return c, max_r - r

    mapping = {}
    for r in range(height):
        for c in range(width):
            r_, c_ = r, c
            max_r, max_c = height - 1, width - 1
            for _ in range(num_rot):
                assert 0 <= r_ <= max_r
                assert 0 <= c_ <= max_c
                r_, c_ = rotate(r_, c_, max_r)
                max_r, max_c = max_c, max_r
            mapping[(city_cells_bbox["min_row"] + r, city_cells_bbox["min_col"] + c)] = r_, c_
    return city_bb, city_cells_bbox, mapping


@router.get("/trajectories/{trajectory_id}/stations")
async def get_trajectory_stations(trajectory_id: str):
    ctx = TrajectoryContext.resolve(trajectory_id)
    env = ctx.get_env()
    return CustomEncodedJSONResponse(content=_build_stations_and_links_payload(env))


@router.get("/trajectories/{trajectory_id}/agents")
async def get_trajectory_agents(trajectory_id: str):
    ctx = TrajectoryContext.resolve(trajectory_id)
    env = ctx.get_env()
    return CustomEncodedJSONResponse(content=_build_agents_content(env))


_DIRECTION_NAMES = {0: "N", 1: "E", 2: "S", 3: "W"}
_DIRECTION_CHARS = {v: k for k, v in _DIRECTION_NAMES.items()}


def _enrich_line(fibre: dict, line_id: int) -> dict:
    # TODO bad code smell avoid splitting
    # fromPin / toPin format: "StationName.DirectionChar.TrackIndex"  e.g. "A.N.0"
    city_from_name, from_dir, from_track = fibre["fromPin"].split(".")
    city_to_name, to_dir, to_track = fibre["toPin"].split(".")
    return {
        **fibre,
        "city_from": city_from_name,
        "city_to": city_to_name,
        "label": f"Line {line_id} ({fibre['fromPin']} → {fibre['toPin']})",
        "start_station_name": f"Station {city_from_name}",
        "end_station_name": f"Station {city_to_name}",
    }


@router.get("/trajectories/{trajectory_id}/lines/")
async def get_trajectory_lines_list(trajectory_id: str):
    ctx = TrajectoryContext.resolve(trajectory_id)
    env = ctx.get_env()
    stations_lines = _build_stations_and_links_payload(env)
    fibres_flat = [fibre for link in stations_lines["links"] for fibre in link["fibres"]]
    return CustomEncodedJSONResponse(content=[
        _enrich_line(fibre, i) for i, fibre in enumerate(fibres_flat)
    ])


@router.get("/trajectories/{trajectory_id}/lines/{line_id}")
async def get_trajectory_lines(trajectory_id: str, line_id: int):
    ctx = TrajectoryContext.resolve(trajectory_id)
    env = ctx.get_env()
    stations_lines = _build_stations_and_links_payload(env)
    fibres_flat = [fibre for link in stations_lines["links"] for fibre in link["fibres"]]
    if line_id < 0 or line_id >= len(fibres_flat):
        raise HTTPException(status_code=404, detail=f"Line {line_id} not found.")
    return CustomEncodedJSONResponse(content=_enrich_line(fibres_flat[line_id], line_id))
