from collections import defaultdict
from typing import Any, List, Dict

import numpy as np
from numpy import dtype, floating, ndarray
from numpy._typing import _64Bit

from flatland.core.grid.grid4_utils import get_direction, is_neighbor_cell
from flatland.core.transition_map import GridTransitionMap
from flatland.envs.grid.rail_env_grid import RailEnvTransitions
from flatland.envs.grid.rail_env_grid import RailEnvTransitionsEnum
from flatland.envs.grid4_generators_utils import connect_rail_in_grid_map
from flatland.envs.rail_env import RailEnv
from flatland.envs.rail_env_shortest_paths import get_k_shortest_paths
from flatland.envs.rail_trainrun_data_structures import Waypoint

_DIRECTION_NAMES = {0: "N", 1: "E", 2: "S", 3: "W"}
_DIRECTION_CHARS = {v: k for k, v in _DIRECTION_NAMES.items()}


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


def _get_new_level(LEVEL: int, num_succ: int) -> int:
    # N.B. left/right is preserved only for 0->1 / 0->-1, for other levels it's always away.
    # N.B. if we have isolated loops, this approach does not well defined:
    #         |--1--------------------|
    #         |  |--1-------------|   |
    #  0 -----|--|--0-------------|---|----
    if num_succ == 1:
        if LEVEL >= 0:
            level_up_or_down = 1
        else:
            level_up_or_down = -1
    else:
        if LEVEL == 0:
            level_up_or_down = -1
        else:
            level_up_or_down = 0
    return level_up_or_down

# TODO pass only env's grid, not env
def extract_link_map(stations_links, current_link, env: RailEnv, fibre_cells: List[tuple]) -> dict:
    start = tuple(fibre_cells[0])
    end = tuple(fibre_cells[-1])
    from_station = current_link["fromStation"]
    from_facing = _DIRECTION_CHARS[current_link["fromFacing"]]
    to_station = current_link["toStation"]
    to_facing = _DIRECTION_CHARS[current_link["toFacing"]]

    zwl_grid = np.zeros(shape=(env.rail.grid.shape[0], env.rail.grid.shape[1] + 50), dtype=int)
    city_1_bb, city_1_cells_bbox, mapping1 = _extract_city_rotated(from_station, from_facing, env, stations_links, 1)
    city_2_bb, city_2_cells_bbox, mapping2 = _extract_city_rotated(to_station, to_facing, env, stations_links, 3)

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

    # mapping so far contains all cells in the two station bb
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

    all_paths = _find_all_paths_between_stations(current_link, env, from_station, stations_links, to_station)

    # cell -> List[tuple[tuple,int]]
    successors_: dict[tuple, set[tuple[tuple, int]]] = {}
    for path in all_paths:
        for wp, wp_after in zip(path, path[1:]):
            successors_.setdefault(wp.position, set()).add((wp_after.position, wp_after.direction - wp.direction))

    # cell -> List[tuple[tuple]] covering all paths between the two gates from left to right; successors are ordered clock-wise
    successors: Dict[tuple, List[tuple]] = {tup: [t[0] for t in sorted(set(successors), key=lambda t: t[1])] for tup, successors in successors_.items()}
    for k, v in successors.items():
        print(k, v)
        print(successors_[k])
        res = []
        for i in v:
            if i not in res:
                res.append(i)
        successors[k] = res
        assert len(res) <= 2, res
    print(f"successors {successors}")

    # cell -> List[tuple[tuple,int]]
    predecessors_: dict[tuple, set[tuple[tuple, int]]] = {}
    for path in all_paths:
        for wp, wp_after in zip(path, path[1:]):
            # TODO this is not well-defined, entering the same edge when entering switch non-pointing can go out same way - or is it no problem?
            predecessors_.setdefault(wp_after.position, set()).add((wp.position, wp_after.direction - wp.direction))

    # cell -> List[tuple[tuple]] covering all paths between the two gates from left to right; predecessors are ordered clock-wise
    predecessors: Dict[tuple, List[tuple]] = {tup: [t[0] for t in sorted(set(predecessors), key=lambda t: t[1])] for tup, predecessors in predecessors_.items()}
    print(f"predecessors {predecessors}")
    for k, v in predecessors.items():
        print(k, v)
        print(predecessors_[k])
        res = []
        for i in v:
            if i not in res:
                res.append(i)
        predecessors[k] = res
        assert len(res) <= 2, res

    # cells in the graph without a mapping assigned yet:
    open_cells = set(successors.keys())
    # for each cell, which level does it have: switches still at same level but next cells have level +1/-1
    levels: dict[tuple, int] = {}
    # for each level, which cells are at the level
    reverse_levels: dict[int, set[tuple]] = defaultdict(set)

    # define level 0:
    print(f"level 0 for fibre cells {fibre_cells}")
    for cell in fibre_cells:
        open_cells.discard(cell)
        levels[cell] = 0
        reverse_levels[0].add(cell)

    _NEIGHBOR_LEVEL = {0: -1, 1: 1}

    print(f"reverse_levels[0]={reverse_levels[0]}")
    print(f"open_cells={open_cells}")
    # TODO iteratively over levels, only 0->1 so far while there are open cells
    for LEVEL in [0, 1, -1]:  # , 2 - 2]:
        if LEVEL not in reverse_levels:
            continue
        reverse_levels_open = defaultdict(set)
        # Assign levels to graph
        for pos in reverse_levels[LEVEL]:
            if pos in successors and len(successors[pos]) == 2:
                print(f"working on {pos} with successors {successors[pos]}")
                for num_succ, succ in enumerate(successors[pos]):
                    level_up_or_down = _get_new_level(LEVEL, num_succ)
                    print(f"working on {pos} with successors {predecessors[pos]}: {succ}")

                    if succ not in open_cells:
                        print(f"{pos} <- {succ} already done")
                        continue
                    print(f"{pos} -> {succ}")
                    levels[succ] = levels[pos] + level_up_or_down
                    reverse_levels_open[levels[pos] + level_up_or_down].add(succ)

            if pos in predecessors and len(predecessors[pos]) == 2:
                print(f"working on {pos} with predecessors {predecessors[pos]}")
                for num_pred, pred in enumerate(predecessors[pos]):
                    level_up_or_down = - _get_new_level(LEVEL, num_pred)
                    print(f"working on {pos} with predecessors {predecessors[pos]}: {pred}")

                    if pred not in open_cells:
                        print(f"{pos} <- {pred} already done")
                        continue
                    print(f"{pos} <- {pred}")
                    levels[pred] = levels[pos] + level_up_or_down
                    reverse_levels_open[levels[pos] + level_up_or_down].add(pred)
        for k, v in reverse_levels_open.items():
            reverse_levels[k].update(v)
        # treat degree 1 within LEVEL
        for pos in reverse_levels[LEVEL]:
            pos_ = pos
            intermediates = []
            while pos_ in successors and len(successors[pos_]) == 1 and (pos_ not in levels or levels.get(pos_, None) == LEVEL):
                levels[pos_] = LEVEL
                intermediates.append(pos_)
                pos_ = successors[pos_][0]
        for pos in reverse_levels[LEVEL]:
            pos_ = pos
            intermediates = []
            while pos_ in predecessors and len(predecessors[pos_]) == 1 and (pos_ not in levels or levels.get(pos_, None) == LEVEL):
                levels[pos_] = LEVEL
                intermediates.append(pos_)
                pos_ = predecessors[pos_][0]

    # Based on levels, map to link map
    for LEVEL in [0, 1, ]:  # -1, 2 - 2]:
        if LEVEL not in reverse_levels:
            continue

        # treat degree 1 out of LEVEL
        if LEVEL != 0:
            for pos in reverse_levels[LEVEL]:
                # TODO follow backwards as well
                if pos in successors and len(successors[pos]) == 1 and pos in mapping:
                    # follow same level ahead:
                    pos_ = pos
                    stretch = []
                    while pos_ in successors and levels.get(pos_) == LEVEL:
                        stretch.append(pos_)
                        next_pos_ = None
                        for s in successors[pos_]:
                            if levels.get(pos_, None) == LEVEL:
                                next_pos_ = s
                                break
                        pos_ = next_pos_

                    to_mapped = mapping.get(stretch[-1], None)
                    from_mapped = mapping[stretch[0]]
                    len_mapped = None
                    if to_mapped is not None:
                        row = from_mapped[0]
                        if row == to_mapped[0]:
                            len_mapped = abs(from_mapped[1] - to_mapped[1]) - 1
                            start_col = min(from_mapped[1], to_mapped[1]) + 1
                            end_col = max(from_mapped[1], to_mapped[1])
                            for c in range(start_col, end_col):
                                trans = zwl_grid_map.grid[(row, c)]
                                trans = zwl_grid_map.transitions.set_transition(trans, 1, 1, 1)
                                trans = zwl_grid_map.transitions.set_transition(trans, 3, 3, 1)
                                print(RailEnvTransitions().print(trans))
                                assert RailEnvTransitions().is_valid(trans)
                                zwl_grid_map.grid[(row, c)] = trans
                        else:
                            pass
                            # TODO when does it happen - ignore?
                    print(f"LEVEL {LEVEL} found stretch {stretch}: {from_mapped} -> {to_mapped}. {len(stretch)} {len_mapped} ")

        # treat degree 2 out of LEVEL
        for pos in reverse_levels[LEVEL]:
            if pos in successors and len(successors[pos]) == 2:
                print(f"working on {pos} with successors {successors[pos]}")
                for num_succ, succ in enumerate(successors[pos]):
                    level_up_or_down = _get_new_level(LEVEL, num_succ)
                    print(f"working on {pos} with successors {predecessors[pos]}: {succ}")

                    if succ not in open_cells:
                        print(f"{pos} <- {succ} already done")
                        continue
                    print(f"{pos} -> {succ}")
                    open_cells.discard(pos)

                    # one row above or below, same column:
                    new_zwl_pos = (mapping[pos][0] + level_up_or_down, mapping[pos][1])
                    if succ not in mapping:
                        print(f"add mapping {succ} -> {new_zwl_pos}")
                        assert zwl_grid[*new_zwl_pos] == 0
                        mapping[succ] = new_zwl_pos
                    else:
                        # happens if pred is a pin
                        pass

                    print(RailEnvTransitionsEnum(env.rail.grid[pos]).name)
                    if RailEnvTransitionsEnum.is_double_slip(env.rail.grid[pos]) or RailEnvTransitionsEnum.is_single_slip(env.rail.grid[pos]):
                        # TODO handle double slips separately
                        continue
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

                    for c in range(mapping[succ][1] + 1, new_zwl_pos[1]):
                        assert zwl_grid[new_zwl_pos[0]][c] == 0
                        zwl_grid[new_zwl_pos[0]][c] = RailEnvTransitionsEnum.horizontal_straight.value
            if pos in predecessors and len(predecessors[pos]) == 2:
                print(f"working on {pos} with predecessors {predecessors[pos]}")
                for num_pred, pred in enumerate(predecessors[pos]):
                    level_up_or_down = - _get_new_level(LEVEL, num_pred)
                    print(f"working on {pos} with predecessors {predecessors[pos]}: {pred}")

                    if pred not in open_cells:
                        print(f"{pos} <- {pred} already done")
                        continue
                    print(f"{pos} <- {pred}")
                    open_cells.discard(pos)

                    # one row above or below, same column:
                    new_zwl_pos = (mapping[pos][0] + level_up_or_down, mapping[pos][1])
                    if pred not in mapping:
                        print(f"add mapping {pred} -> {new_zwl_pos}")
                        # TODO why?
                        # assert zwl_grid[*new_zwl_pos] == 0
                        mapping[pred] = new_zwl_pos
                    else:
                        # happens if pred is a pin
                        pass

                    # TODO temp workaround seed 45
                    # print(RailEnvTransitionsEnum(env.rail.grid[pos]).name)
                    # if RailEnvTransitionsEnum.is_double_slip(env.rail.grid[pos]) or RailEnvTransitionsEnum.is_single_slip(env.rail.grid[pos]):
                    #     # TODO handle double slips separtely
                    #     continue

                    trans = zwl_grid_map.grid[*mapping[pos]]
                    print(RailEnvTransitionsEnum(trans).name)
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
                    # TODO curves wrong works only for level 0?
                    if level_up_or_down == 1:
                        # up: E-N curve
                        zwl_grid_map.grid[*new_zwl_pos] = RailEnvTransitionsEnum.right_turn_from_north.value
                    else:
                        # down: E-S curve
                        zwl_grid_map.grid[*new_zwl_pos] = RailEnvTransitionsEnum.right_turn_from_west.value

                    for c in range(mapping[pred][1] + 1, new_zwl_pos[1]):
                        assert zwl_grid[new_zwl_pos[0]][c] == 0
                        zwl_grid[new_zwl_pos[0]][c] = RailEnvTransitionsEnum.horizontal_straight.value

    # treat incoming/outgoing from all paths
    print(f"find crossings")
    print(fibre_cells)
    for cell in successors.keys():
        # TODO temp workaround seed 45
        # continue
        # find missing neighbors
        pairs = env.rail.get_neighbor_pairs(cell)

        new_neighbors = {p for pair in pairs for p in pair if p not in mapping}
        above = (mapping[cell][0] - 1, mapping[cell][1])
        below = (mapping[cell][0] + 1, mapping[cell][1])
        assert cell not in new_neighbors
        chosen = None
        not_chosen = None

        if len(new_neighbors) == 2:
            assert zwl_grid_map.grid[*above] == 0
            assert zwl_grid_map.grid[*below] == 0

            # randomly assign neighbors to above and below
            for n, mapped in zip(new_neighbors, [above, below]):
                assert n not in mapping
                mapping[n] = mapped
        elif len(new_neighbors) == 1:
            if zwl_grid_map.grid[*above] == 0:
                chosen = above
                not_chosen = below
            elif zwl_grid_map.grid[*below] == 0:
                chosen = below
                not_chosen = above
            else:
                # TODO add warning instead?
                raise
            assert zwl_grid_map.grid[*chosen] == 0
            n = list(new_neighbors)[0]
            assert n not in mapping
            mapping[n] = chosen

        # in zwl add transitions for mapped neighbor pairs
        trans = zwl_grid_map.grid[*mapping[*cell]]
        for from_cell, to_cell in pairs:
            if is_neighbor_cell(mapping[from_cell], mapping[cell]) and is_neighbor_cell(mapping[cell], mapping[to_cell]):
                trans = zwl_grid_map.transitions.set_transition(trans, get_direction(mapping[from_cell], mapping[cell]),
                                                                get_direction(mapping[cell], mapping[to_cell]), 1)
            else:
                # try to fix using not_chosen
                if not_chosen is not None and zwl_grid_map.grid[*not_chosen] == 0:
                    if is_neighbor_cell(mapping[from_cell], mapping[cell]) and not is_neighbor_cell(mapping[cell], mapping[to_cell]):

                        trans = zwl_grid_map.transitions.set_transition(trans, get_direction(mapping[from_cell], mapping[cell]),
                                                                        get_direction(mapping[cell], not_chosen), 1)
                        # TODO make sure the fake neighbor cannot be used any more as its transitions are  0
                    elif not is_neighbor_cell(mapping[from_cell], mapping[cell]) and is_neighbor_cell(mapping[cell], mapping[to_cell]):

                        trans = zwl_grid_map.transitions.set_transition(trans, get_direction(not_chosen, mapping[cell]),
                                                                        get_direction(mapping[cell], mapping[to_cell]), 1)
                        # TODO make sure the fake neighbor cannot be used any more as its transitions are 0
                else:
                    # edge case: we're passing a pin (that is already mapped and connected to us with intermediate cells)
                    if RailEnvTransitionsEnum.is_double_slip(env.rail.grid[cell]):
                        # grid
                        all_neighbors_zwl = {(mapping[cell][0] + offset[0], mapping[cell][1] + offset[1]) for offset in [(0, 1), (1, 0), (0, -1), (-1, 0)]}

                        replacement = all_neighbors_zwl.difference(set(mapping.values()))
                        assert len(replacement) == 1
                        replacement = list(replacement)[0]

                        if is_neighbor_cell(mapping[from_cell], mapping[cell]) and not is_neighbor_cell(mapping[cell], mapping[to_cell]):
                            trans = zwl_grid_map.transitions.set_transition(trans, get_direction(mapping[from_cell], mapping[cell]),
                                                                            get_direction(mapping[cell], replacement), 1)

                            pass
                        elif RailEnvTransitionsEnum.is_double_slip(env.rail.grid[cell]) and not is_neighbor_cell(mapping[from_cell],
                                                                                                                 mapping[cell]) and is_neighbor_cell(
                            mapping[cell], mapping[to_cell]):
                            trans = zwl_grid_map.transitions.set_transition(trans, get_direction(replacement, mapping[cell]),
                                                                            get_direction(mapping[cell], mapping[to_cell]), 1)
                        else:
                            # TODO ignore and add warning instead?
                            raise

                    if len(new_neighbors) > 0:
                        # TODO add warning
                        print("ignoring")
        print(RailEnvTransitions().print(trans))
        if RailEnvTransitions().is_valid(trans):
            zwl_grid_map.grid[*mapping[*cell]] = trans
        else:
            orig = RailEnvTransitionsEnum(env.rail.grid[*cell])
            mapped = RailEnvTransitionsEnum(zwl_grid_map.grid[*mapping[*cell]])
            print(orig)
            print(mapped)
            # TODO add warning instead?
            raise

    # TODO document behaviour where this approach does not reflect the grid faithfully -> add sanity check, that the graph remains the same and fail/inform when the link map does not reflect the grid faithfully?
    content = {
        # ZWL grid
        "grid": zwl_grid,
        # env -> ZWL coordindates
        "mapping": [[[r, pos], list(v)] for (r, pos), v in mapping.items()],
        "city_cells_bbox": city_1_cells_bbox,
        "levels": [[list(k), v] for k, v in levels.items()],
    }

    return content


def _find_all_paths_between_stations(current_link, env: RailEnv, from_station, stations_links, to_station) -> list[list[Waypoint]]:
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
    return all_paths


def _within_bbox(city_bbox, cell: tuple[Any, Any]) -> Any:
    return city_bbox["min_row"] <= cell[0] <= city_bbox["max_row"] and city_bbox["min_col"] <= cell[1] <= city_bbox["max_col"]


def _within_bbox_excl_boundary(city_bbox, cell: tuple[Any, Any]) -> Any:
    return city_bbox["min_row"] < cell[0] < city_bbox["max_row"] and city_bbox["min_col"] < cell[1] < city_bbox["max_col"]


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
