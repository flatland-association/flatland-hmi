import asyncio
import json
from collections import defaultdict
from fractions import Fraction
from json import JSONEncoder
from pathlib import Path
from typing import Any, Optional, List, Dict

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
from envs.grid.rail_env_grid import RailEnvTransitionsEnum
from envs.rail_env_shortest_paths import get_k_shortest_paths
from flatland.core.transition_map import GridTransitionMap
from flatland.envs.grid.rail_env_grid import RailEnvTransitions
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

    station_gates = {i: {gate_key: {"name": gate["name"],
                                    "pins": {k: {"name": v["name"], "node": v["node"]} for k, v in gate["pins"].items()}} for gate_key, gate in
                         v["gates"].items()} for i, v
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


@router.get("/trajectories/{trajectory_id}/zwl/{link_id}")
async def get_trajectory_agent_transitions(trajectory_id: str, link_id: int):
    ctx = TrajectoryContext.resolve(trajectory_id)
    env = ctx.get_env()
    stations_links = _build_stations_and_links_payload(env)
    print("stations_links")
    print(stations_links)
    links = stations_links["links"]
    if link_id < 0 or link_id >= len(links):
        raise HTTPException(status_code=404, detail=f"Link {link_id} not found.")

    current_link = links[link_id]
    fibre = current_link["fibres"][0]
    print("fibre")
    print(fibre)
    fibre_cells = fibre["cells"]
    content = _extract_link_map(stations_links, current_link, env, fibre_cells)
    return CustomEncodedJSONResponse(content=content)


# TODO pass only env's grid, not env
def _extract_link_map(stations_links, current_link, env: RailEnv, fibre_cells: List[tuple]) -> dict:
    start = tuple(fibre_cells[0])
    end = tuple(fibre_cells[-1])
    from_station = current_link["fromStation"]
    from_facing = _DIRECTION_CHARS[current_link["fromFacing"]]
    to_station = current_link["toStation"]
    to_facing = _DIRECTION_CHARS[current_link["toFacing"]]

    zwl_grid = np.zeros(shape=(env.rail.grid.shape[0], env.rail.grid.shape[1] + 50), dtype=int)
    city_1_bb, city_cells_bbox, mapping1 = _extract_city_rotated(from_station, from_facing, env, stations_links, 1)
    city_2_bb, city_cells_bbox, mapping2 = _extract_city_rotated(to_station, to_facing, env, stations_links, 3)

    start_y = mapping1[start][0]
    end_y = mapping2[end][0]
    straight_y = max(start_y, end_y)
    x_offset_1 = 0
    y_offset_1 = 0
    if start_y < straight_y:
        y_offset_1 = straight_y - start_y
    zwl_grid[y_offset_1:city_1_bb.shape[0] + y_offset_1, :city_1_bb.shape[1]] = city_1_bb
    mapping1 = {k: (r + y_offset_1, pos + x_offset_1) for k, (r, pos) in mapping1.items()}

    y_offset_2 = 00
    # first and last cell of line in stations bb
    x_offset_2 = city_1_bb.shape[1] + len(fibre_cells) - 2
    if end_y < straight_y:
        y_offset_2 = straight_y - end_y
    zwl_grid[y_offset_2:city_2_bb.shape[0] + y_offset_2, x_offset_2:city_2_bb.shape[1] + x_offset_2] = city_2_bb

    zwl_grid = zwl_grid[:max(city_1_bb.shape[0] + y_offset_1, city_2_bb.shape[0] + y_offset_2), :x_offset_2 + city_2_bb.shape[1]]

    mapping2 = {k: (r + y_offset_2, pos + x_offset_2) for k, (r, pos) in mapping2.items()}

    mapping = {**mapping1, **mapping2}
    print(f"mapping {mapping}")

    zwl_grid_map = GridTransitionMap(height=zwl_grid.shape[0], width=zwl_grid.shape[1], transitions=RailEnvTransitions(), grid=zwl_grid)
    path = connect_rail_in_grid_map(
        grid_map=zwl_grid_map,
        rail_trans=RailEnvTransitions(),
        start=mapping[start],
        end=mapping[end],
    )
    print("path")
    print(path)
    assert path[0] == mapping[start]
    assert path[-1] == mapping[end]
    assert len(fibre_cells) == len(path)
    print("fibre")
    print(fibre_cells)
    for i, cell in enumerate(path):
        mapping[fibre_cells[i]] = cell

    print("station_gates:")
    for station in stations_links["station_gates"].values():
        for gate in station.values():
            print(gate)

    grid_without_stations = env.rail.grid.copy()
    pin_cells = [pin["node"] for station in stations_links["station_gates"].values() for gate in station.values() for pin in gate["pins"].values()]
    print("pin_cells")
    print(pin_cells)
    for cells in stations_links["station_edges"].values():
        for cell in cells:
            if cell in pin_cells:
                continue
            grid_without_stations[cell[0]][cell[1]] = 0
    grid_map_without_stations = GridTransitionMap(height=grid_without_stations.shape[0], width=grid_without_stations.shape[1], transitions=RailEnvTransitions(),
                                                  grid=grid_without_stations)

    from_pins = [(p["node"], _DIRECTION_CHARS[current_link["fromFacing"]]) for p in
                 stations_links["station_gates"][from_station][current_link["fromFacing"]]["pins"].values()]
    to_pins = [(p["node"], _DIRECTION_CHARS[current_link["fromFacing"]]) for p in
               stations_links["station_gates"][to_station][current_link["toFacing"]]["pins"].values()]

    print(f"from_pins={from_pins}")
    print(f"to_pins={to_pins}")
    all_paths: List[List[Waypoint]] = []
    for (source_position, source_direction) in from_pins:
        for target_position, target_direction in to_pins:
            paths = get_k_shortest_paths(None, rail=grid_map_without_stations,
                                         source_position=source_position,
                                         source_direction=source_direction,
                                         target_position=target_position, k=10)
            print(f"found {source_position}, {source_direction}, {target_position}, {target_direction}: {paths}")
            all_paths.extend(paths)

    successors: dict[tuple, set[tuple[tuple, int]]] = {}
    for path in all_paths:
        for wp, wp_after in zip(path, path[1:]):
            successors.setdefault(wp.position, set()).add((wp_after.position, wp_after.direction - wp.direction))

    # cell -> List[tuple[tuple,int]] covering all paths between the two gates; successors are ordered clock-wise
    successors: Dict[tuple, List[tuple]] = {tup: [t[0] for t in sorted(successors, key=lambda t: t[1])] for tup, successors in successors.items()}
    print(f"successors {successors}")

    predecessors: dict[tuple, set[tuple[tuple, int]]] = {}
    for path in all_paths:
        for wp, wp_after in zip(path, path[1:]):
            predecessors.setdefault(wp_after.position, set()).add((wp.position, wp_after.direction - wp.direction))

    # cell -> List[tuple[tuple,int]] covering all paths between the two gates; predecessors are ordered clock-wise
    predecessors: Dict[tuple, List[tuple]] = {tup: [t[0] for t in sorted(predecessors, key=lambda t: t[1])] for tup, predecessors in predecessors.items()}
    print(f"predecessors {predecessors}")

    # cells in the graph without a level assigned yet:
    open_cells = set(successors.keys())
    # for each cell, which level does it have: switches still at same level but next cells have level +1/-1
    levels: dict[tuple, int] = {}
    # for each level, which cells are at the level
    reverse_levels: dict[int, set[tuple]] = defaultdict(set)

    # define level 0:
    for cell in fibre_cells:
        open_cells.discard(cell)
        levels[cell] = 0
        reverse_levels[0].add(cell)

    _NEIGHBOR_LEVEL = {0: -1, 1: 1}

    print(f"reverse_levels[0]={reverse_levels[0]}")
    print(f"open_cells={open_cells}")
    # TODO iteratively over levels, only 0->1 so far
    for pos in reverse_levels[0]:
        if pos in successors and len(successors[pos]) == 2:
            print(f"working on {pos} with successors {successors[pos]}")
            for num_succ, succ in enumerate(successors[pos]):
                if num_succ == 1:
                    level_up_or_down = 1
                else:
                    level_up_or_down = -1
                print(f"working on {pos} with successors {predecessors[pos]}: {succ}")

                if succ not in open_cells:
                    print(f"{pos} <- {succ} already done")
                    continue
                print(f"{pos} -> {succ}")
                levels[succ] = levels[pos] + level_up_or_down
                reverse_levels[levels[pos] + level_up_or_down].add(succ)
                open_cells.discard(succ)

                # one row above or below, same column:
                new_zwl_pos = (mapping[pos][0] + level_up_or_down, mapping[pos][1])
                if succ not in mapping:
                    print(f"add mapping {succ} -> {new_zwl_pos}")
                    assert zwl_grid[*new_zwl_pos] == 0
                    mapping[succ] = new_zwl_pos
                else:
                    # happens if pred is a pin
                    pass

                trans = zwl_grid_map.grid[*mapping[pos]]
                print(RailEnvTransitions().print(trans))

                # on pos, add transition: if +1, add N-E trans, if -1 add S-E trans
                if level_up_or_down == 1:
                    # from right to down:
                    trans = zwl_grid_map.transitions.set_transition(trans, 1, 2, 1)
                    trans = zwl_grid_map.transitions.set_transition(trans, 0, 3, 1)
                else:
                    # from right to up:
                    trans = zwl_grid_map.transitions.set_transition(trans, 1, 0, 1)
                    trans = zwl_grid_map.transitions.set_transition(trans, 2, 3, 1)
                print(RailEnvTransitions().print(trans))
                assert RailEnvTransitions().is_valid(trans)
                zwl_grid_map.grid[*mapping[pos]] = trans

                # on pred, add curve: if +1, add E-N curve, if -1 add E-S curve
                if level_up_or_down == 1:
                    # up: S-E curve
                    zwl_grid_map.grid[*new_zwl_pos] = RailEnvTransitionsEnum.right_turn_from_east.value
                else:
                    # down: N-E curve
                    zwl_grid_map.grid[*new_zwl_pos] = RailEnvTransitionsEnum.right_turn_from_south.value

                # TODO unit test. how

                pred_preds = predecessors.get(succ, [])

                print("pred_preds")
                print(pred_preds)
                pred_pred = None
                intermediates = []
                while len(pred_preds) == 1:
                    print(pred_preds)
                    pred_pred = pred_preds.pop()
                    intermediates.append(pred_pred)
                    pred_preds = predecessors.get(pred_pred, [])
                if pred_pred is not None:
                    p = connect_rail_in_grid_map(
                        grid_map=zwl_grid_map,
                        rail_trans=RailEnvTransitions(),
                        start=mapping[pred_pred],
                        end=new_zwl_pos,
                    )
                    print(p)
                else:
                    # TODO connect_rail_in_grid_map seems not to always work as expected, so handle this case gracefully:
                    if new_zwl_pos[0] == mapping[succ][0]:
                        for c in range(mapping[succ][1] + 1, new_zwl_pos[1]):
                            assert zwl_grid[new_zwl_pos[0]][c] == 0
                            zwl_grid[new_zwl_pos[0]][c] = RailEnvTransitionsEnum.horizontal_straight.value
                    else:
                        connect_rail_in_grid_map(
                            grid_map=zwl_grid_map,
                            rail_trans=RailEnvTransitions(),
                            start=mapping[succ],
                            end=new_zwl_pos,
                        )

                # TODO add mapping for all intermediates!

        if pos in predecessors and len(predecessors[pos]) == 2:

            print(f"working on {pos} with predecessors {predecessors[pos]}")
            for num_succ, succ in enumerate(predecessors[pos]):
                if num_succ == 0:
                    level_up_or_down = 1
                else:
                    level_up_or_down = -1
                print(f"working on {pos} with predecessors {predecessors[pos]}: {succ}")

                if succ not in open_cells:
                    print(f"{pos} <- {succ} already done")
                    continue
                print(f"{pos} <- {succ}")
                levels[succ] = levels[pos] + level_up_or_down
                reverse_levels[levels[pos] + level_up_or_down].add(succ)
                open_cells.discard(succ)

                # one row above or below, same column:
                new_zwl_pos = (mapping[pos][0] + level_up_or_down, mapping[pos][1])
                if succ not in mapping:
                    print(f"add mapping {succ} -> {new_zwl_pos}")
                    assert zwl_grid[*new_zwl_pos] == 0
                    mapping[succ] = new_zwl_pos
                else:
                    # happens if pred is a pin
                    pass

                trans = zwl_grid_map.grid[*mapping[pos]]
                print(RailEnvTransitions().print(trans))
                # on pos, add transition: if +1, add N-E trans, if -1 add S-E trans
                if level_up_or_down == 1:
                    # from up to right:
                    trans = zwl_grid_map.transitions.set_transition(trans, 0, 1, 1)
                    trans = zwl_grid_map.transitions.set_transition(trans, 3, 2, 1)
                else:
                    # from down to right:
                    trans = zwl_grid_map.transitions.set_transition(trans, 2, 1, 1)
                    trans = zwl_grid_map.transitions.set_transition(trans, 3, 0, 1)
                print(RailEnvTransitions().print(trans))
                assert RailEnvTransitions().is_valid(trans)
                zwl_grid_map.grid[*mapping[pos]] = trans

                # on pred, add curve: if +1, add E-N curve, if -1 add E-S curve
                if level_up_or_down == 1:
                    # up: E-N curve
                    zwl_grid_map.grid[*new_zwl_pos] = RailEnvTransitionsEnum.right_turn_from_north.value
                else:
                    # down: E-S curve
                    zwl_grid_map.grid[*new_zwl_pos] = RailEnvTransitionsEnum.right_turn_from_west.value

                # TODO unit test. how

                pred_preds = predecessors.get(succ, [])

                print("pred_preds")
                print(pred_preds)
                pred_pred = None
                intermediates = []
                while len(pred_preds) == 1:
                    print(pred_preds)
                    pred_pred = pred_preds.pop()
                    intermediates.append(pred_pred)
                    pred_preds = predecessors.get(pred_pred, [])
                if pred_pred is not None:
                    p = connect_rail_in_grid_map(
                        grid_map=zwl_grid_map,
                        rail_trans=RailEnvTransitions(),
                        start=mapping[pred_pred],
                        end=new_zwl_pos,
                    )
                    print(p)
                else:
                    # TODO connect_rail_in_grid_map seems not to always work as expected, so handle this case gracefully:
                    if new_zwl_pos[0] == mapping[succ][0]:
                        for c in range(mapping[succ][1] + 1, new_zwl_pos[1]):
                            assert zwl_grid[new_zwl_pos[0]][c] == 0
                            zwl_grid[new_zwl_pos[0]][c] = RailEnvTransitionsEnum.horizontal_straight.value
                    else:
                        connect_rail_in_grid_map(
                            grid_map=zwl_grid_map,
                            rail_trans=RailEnvTransitions(),
                            start=mapping[succ],
                            end=new_zwl_pos,
                        )

                # TODO add mapping for all intermediates!

    print(f"successors={successors}")
    print(f"predecessor={predecessors}")
    print(f"levels={levels}")
    print(f"reverse_levels={reverse_levels}")
    print(f"reverse_levels[1]={reverse_levels[1]}")
    # TODO find switches/crossing leaving the paths
    content = {
        # ZWL grid
        "grid": zwl_grid,
        # env -> ZWL coordindates
        "mapping": [[[r, pos], list(v)] for (r, pos), v in mapping.items()],
        "city_cells_bbox": city_cells_bbox,
    }

    return content


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


def _enrich_line(link: dict, link_id: int) -> dict:
    return {
        "cityFrom": link["fromStation"],
        "cityTo": link["toStation"],
        "label": f"Link {link_id} ({link['fromGate']} → {link['toGate']})",
        "startStationName": f"Station {link['fromStation']}",
        "endStationName": f"Station {link['toStation']}",
    }


@router.get("/trajectories/{trajectory_id}/links/")
async def get_trajectory_lines_list(trajectory_id: str):
    ctx = TrajectoryContext.resolve(trajectory_id)
    env = ctx.get_env()
    stations_lines = _build_stations_and_links_payload(env)
    links = stations_lines["links"]
    return CustomEncodedJSONResponse(content=[
        _enrich_line(link, i) for i, link in enumerate(links)
    ])


@router.get("/trajectories/{trajectory_id}/links/{link_id}")
async def get_trajectory_lines(trajectory_id: str, link_id: int):
    ctx = TrajectoryContext.resolve(trajectory_id)
    env = ctx.get_env()
    stations_lines = _build_stations_and_links_payload(env)
    links = stations_lines["links"]
    if link_id < 0 or link_id >= len(links):
        raise HTTPException(status_code=404, detail=f"Link {link_id} not found.")
    return CustomEncodedJSONResponse(content=_enrich_line(links[link_id], link_id))
