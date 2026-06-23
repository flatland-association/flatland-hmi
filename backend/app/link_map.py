from collections import defaultdict
from typing import Any, List, Dict

import numpy as np
from numpy import dtype, floating, ndarray
from numpy._typing import _64Bit

from flatland.core.transition_map import GridTransitionMap
from flatland.envs.grid.rail_env_grid import RailEnvTransitions
from flatland.envs.grid.rail_env_grid import RailEnvTransitionsEnum
from flatland.envs.grid4_generators_utils import connect_rail_in_grid_map
from flatland.envs.rail_env import RailEnv
from flatland.envs.rail_env_shortest_paths import get_k_shortest_paths
from flatland.envs.rail_trainrun_data_structures import Waypoint

_DIRECTION_NAMES = {0: "N", 1: "E", 2: "S", 3: "W"}
_DIRECTION_CHARS = {v: k for k, v in _DIRECTION_NAMES.items()}


# TODO in Block build add gate, not only station as label
# TODO inspect more results on more randomly generated envs and on competition topology maybe
def build_stations_and_links_payload(env) -> dict:
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


# TODO pass only env's grid, not env
def extract_link_map(stations_links, current_link, env: RailEnv, fibre_cells: List[tuple]) -> dict:
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
    # TODO document behaviour where this approach does not reflect the grid faithfully -> add sanity check, that the graph remains the same and fail/inform when the link map does not reflect the grid faithfully?
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
