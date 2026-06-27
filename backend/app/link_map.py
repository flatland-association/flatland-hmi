from collections import defaultdict
from typing import Any, List, Dict

import numpy as np
from numpy import dtype, floating, ndarray
from numpy._typing import _64Bit

from flatland.core.grid.grid4_utils import get_direction, is_neighbor_cell, mirror
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


def _assign_level(cell: tuple, level: int, levels: dict, reverse_levels: dict) -> None:
    if cell in levels:
        assert levels[cell] == level
        return
    levels[cell] = level
    reverse_levels[level].add(cell)


def _get_next_level(LEVEL: int, num_succ: int, succ, baseline_succ) -> int:
    # N.B. left/right is preserved only for 0->1 / 0->-1, for other levels it's always away.
    # N.B. if we have isolated loops, this approach does not well defined:
    #         |--1--------------------|
    #         |  |--1-------------|   |
    #  0 -----|--|--0-------------|---|----
    print(f"_get_next_level({LEVEL}, {num_succ}, {succ}, {baseline_succ})")
    if LEVEL == 0:
        if baseline_succ == succ:
            return 0
        # preserve left/right away from baseline fibre
        # if I'm not baseline and clockwise +1 -> right -> level +1
        return 1 if num_succ == 1 else -1
    else:
        if num_succ == 1:
            # always branch away from baseline fibre
            return 1 if LEVEL > 0 else -1
        else:
            return 0


# TODO pass only env's grid, not env
def extract_link_map(stations_links, current_link, env: RailEnv, fibre_cells: List[tuple]) -> dict:
    start = tuple(fibre_cells[0])
    end = tuple(fibre_cells[-1])
    from_pin = next((f["fromPin"] for f in current_link["fibres"] if tuple(f["cells"][0]) == start), None)
    to_pin = next((f["toPin"] for f in current_link["fibres"] if tuple(f["cells"][-1]) == end), None)
    from_station = current_link["fromStation"]
    from_facing = _DIRECTION_CHARS[current_link["fromFacing"]]
    to_station = current_link["toStation"]
    to_facing = _DIRECTION_CHARS[current_link["toFacing"]]
    from_gate = next(
        (gate for gate in stations_links["station_gates"][from_station].values()
         if any(tuple(pin["node"]) == start for pin in gate["pins"].values())),
        None
    )
    from_gate_name = from_gate["name"] if from_gate else None
    from_pin_index = next(
        (i for i, pin in enumerate(from_gate["pins"].values()) if tuple(pin["node"]) == start),
        None
    ) if from_gate else None

    to_gate = next(
        (gate for gate in stations_links["station_gates"][to_station].values()
         if any(tuple(pin["node"]) == end for pin in gate["pins"].values())),
        None
    )
    to_gate_name = to_gate["name"] if to_gate else None
    to_pin_index = next(
        (i for i, pin in enumerate(to_gate["pins"].values()) if tuple(pin["node"]) == end),
        None
    ) if to_gate else None

    print(
        f"from_pin={from_pin},from_gate={from_gate_name}, from_pin_index={from_pin_index}, to_pin={to_pin},to_gate={to_gate_name}, to_pin_index={to_pin_index}")

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
    mapping_from_to_station = {**mapping1, **mapping2}

    _from_to_gate_pin_nodes = {
        tuple(pin["node"])
        for gate in [from_gate, to_gate]
        if gate
        for pin in gate["pins"].values()
    }
    _other_station_pin_nodes = {
                                   tuple(pin["node"])
                                   for station_name in [from_station, to_station]
                                   for gate in stations_links["station_gates"][station_name].values()
                                   for pin in gate["pins"].values()
                               } - _from_to_gate_pin_nodes
    mapping_only_pins_from_stations = {
        k: v
        for k, v in mapping_from_to_station.items()
        if k not in _other_station_pin_nodes
    }
    print(f"pin_to_zwl={mapping_only_pins_from_stations}")

    print(f"mapping {mapping_only_pins_from_stations}")

    zwl_grid_map = GridTransitionMap(height=zwl_grid.shape[0], width=zwl_grid.shape[1], transitions=RailEnvTransitions(), grid=zwl_grid)
    path = connect_rail_in_grid_map(
        grid_map=zwl_grid_map,
        rail_trans=RailEnvTransitions(),
        start=mapping_only_pins_from_stations[start],
        end=mapping_only_pins_from_stations[end],
    )
    print("path")
    print(path)
    assert path[0] == mapping_only_pins_from_stations[start]
    assert path[-1] == mapping_only_pins_from_stations[end]
    assert len(fibre_cells) == len(path)
    print("fibre")
    print(fibre_cells)
    for i, cell in enumerate(path):
        mapping_only_pins_from_stations[fibre_cells[i]] = cell

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
            # +1 means to to the right forward
            # -1 means to the left forward
            direction_change = (wp_after.direction - wp.direction) % 4
            assert direction_change in {0, 1, 3}
            if direction_change == 3:
                direction_change = -1
            predecessors_.setdefault(wp_after.position, set()).add((wp.position, direction_change))

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
        _assign_level(cell, 0, levels, reverse_levels)

    # add levels to from and to pin (might not be covered by paths)
    baseline_row = mapping_only_pins_from_stations[fibre_cells[0]][0]
    for level, pin in zip(range(-from_pin_index, len(from_gate["pins"]) - from_pin_index + 1), from_gate["pins"].values()):
        level = mapping_only_pins_from_stations[pin["node"]][0] - baseline_row
        _assign_level(tuple(pin["node"]), level, levels, reverse_levels)
    for level, pin in zip(range(-to_pin_index, len(to_gate["pins"]) - to_pin_index + 1), to_gate["pins"].values()):
        level = mapping_only_pins_from_stations[pin["node"]][0] - baseline_row
        _assign_level(tuple(pin["node"]), level, levels, reverse_levels)

    _NEIGHBOR_LEVEL = {0: -1, 1: 1}

    print(f"reverse_levels[0]={reverse_levels[0]}")
    print(f"open_cells={open_cells}")
    # Iteratively, assign levels to graph (all paths between chosen link's gates)
    for LEVEL in [0, 1, -1, 2 - 2]:
        if LEVEL not in reverse_levels:
            continue
        reverse_levels_open = defaultdict(set)

        for pos in reverse_levels[LEVEL]:
            if pos in successors and len(successors[pos]) == 2:
                print(f"working on {pos} with successors {successors[pos]}")
                for num_succ, succ in enumerate(successors[pos]):
                    level_up_or_down = _get_next_level(LEVEL, num_succ, succ, _get_succ_at_same_level(LEVEL, levels, pos, successors))
                    print(f"working on {pos} with successors {predecessors[pos]}: {succ} -> {level_up_or_down} {successors_[pos]}")

                    if succ not in open_cells:
                        print(f"{pos} <- {succ} already done")
                        continue
                    print(f"{pos} -> {succ}")

                    _assign_level(succ, levels[pos] + level_up_or_down, levels, reverse_levels_open)

            if pos in predecessors and len(predecessors[pos]) == 2:
                print(f"working on {pos} with predecessors {predecessors[pos]}")
                for num_pred, pred in enumerate(predecessors[pos]):
                    level_up_or_down = - _get_next_level(LEVEL, num_pred, pred, _get_succ_at_same_level(LEVEL, levels, pos, predecessors))
                    print(f"working on {pos} with predecessors {predecessors[pos]}: {pred} -> {level_up_or_down} {predecessors_[pos]}")

                    if pred not in open_cells:
                        print(f"{pos} <- {pred} already done")
                        continue
                    print(f"{pos} <- {pred}")
                    _assign_level(pred, levels[pos] + level_up_or_down, levels, reverse_levels_open)
        for k, v in reverse_levels_open.items():
            reverse_levels[k].update(v)
        # treat degree 1 within LEVEL
        for pos in list(reverse_levels[LEVEL]):
            pos_ = pos
            while pos_ in successors and len(successors[pos_]) == 1 and (pos_ not in levels or levels.get(pos_, None) == LEVEL):
                _assign_level(pos_, LEVEL, levels, reverse_levels)
                pos_ = successors[pos_][0]
        for pos in list(reverse_levels[LEVEL]):
            pos_ = pos
            while pos_ in predecessors and len(predecessors[pos_]) == 1 and (pos_ not in levels or levels.get(pos_, None) == LEVEL):
                _assign_level(pos_, LEVEL, levels, reverse_levels)
                pos_ = predecessors[pos_][0]

    # Based on levels, map to link map
    # TODO fix -2/2 etc.why does it fail?
    for LEVEL in [0, 1, -1]:  # , 2 - 2]:
        if LEVEL not in reverse_levels:
            continue

        # treat degree 1 out of LEVEL -> connect the level
        # if LEVEL == 0:
        #     for cell in reverse_levels[LEVEL]:
        #         _handle_slips(cell, env, mapping, zwl_grid_map, levels, reverse_levels, random_allowed=True)
        if LEVEL != 0:
            for pos in reverse_levels[LEVEL]:
                # TODO follow backwards as well? Maybe not necessary as we say within the graph where everything is forward reachable!
                if pos in successors and len(successors[pos]) == 1 and pos in mapping_only_pins_from_stations:
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

                    to_mapped = mapping_only_pins_from_stations.get(stretch[-1], None)
                    from_mapped = mapping_only_pins_from_stations[stretch[0]]
                    len_mapped = None
                    if to_mapped is not None:
                        row = from_mapped[0]
                        if row == to_mapped[0]:
                            len_mapped = abs(from_mapped[1] - to_mapped[1]) - 1
                            start_col = min(from_mapped[1], to_mapped[1]) + 1
                            end_col = max(from_mapped[1], to_mapped[1])
                            for i, c in enumerate(range(start_col, end_col)):
                                trans = zwl_grid_map.grid[(row, c)]
                                trans = zwl_grid_map.transitions.set_transition(trans, 1, 1, 1)
                                trans = zwl_grid_map.transitions.set_transition(trans, 3, 3, 1)
                                print(RailEnvTransitions().print(trans))
                                assert RailEnvTransitions().is_valid(trans)
                                zwl_grid_map.grid[(row, c)] = trans
                                index = int((i / len_mapped) * len(stretch))
                                print(f"XXX {index} add mapping[{stretch[index]}]={(row, c)}")
                                # TODO safe?
                                if stretch[index] not in mapping_only_pins_from_stations:
                                    mapping_only_pins_from_stations[stretch[index]] = (row, c)

                        else:
                            pass
                            # TODO when does it happen - ignore?
                    print(f"LEVEL {LEVEL} found stretch {stretch}: {from_mapped} -> {to_mapped}. {len(stretch) - 2} {len_mapped} ")

        # treat degree 2 out of LEVEL
        for pos in reverse_levels[LEVEL]:
            if pos in successors and len(successors[pos]) == 2:
                print(f"working on {pos} with successors {successors[pos]}")
                for num_succ, succ in enumerate(successors[pos]):
                    # TODO bad code smell - levels should already be assigned!
                    level_up_or_down = _get_next_level(LEVEL, num_succ, succ, _get_succ_at_same_level(LEVEL, levels, pos, successors))
                    print(f"working on {pos} with successors {predecessors[pos]}: {succ}")

                    if succ not in open_cells:
                        print(f"{pos} <- {succ} already done")
                        continue
                    print(f"{pos} -> {succ}")
                    open_cells.discard(pos)

                    # one row above or below, same column:
                    new_zwl_pos = (mapping_only_pins_from_stations[pos][0] + level_up_or_down, mapping_only_pins_from_stations[pos][1])
                    if succ not in mapping_only_pins_from_stations:
                        print(f"add mapping {succ} -> {new_zwl_pos}")
                        assert zwl_grid[*new_zwl_pos] == 0
                        mapping_only_pins_from_stations[succ] = new_zwl_pos
                    else:
                        # happens if pred is a pin
                        pass

                    trans = zwl_grid_map.grid[*mapping_only_pins_from_stations[pos]]
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
                    zwl_grid_map.grid[*mapping_only_pins_from_stations[pos]] = trans

                    # on pred, add curve: if +1, add E-N curve, if -1 add E-S curve
                    print(f"curve on {new_zwl_pos}")
                    if level_up_or_down == 1:
                        # up: S-E curve
                        zwl_grid_map.grid[*new_zwl_pos] = RailEnvTransitionsEnum.right_turn_from_east.value
                    elif level_up_or_down == -1:
                        # down: N-E curve
                        zwl_grid_map.grid[*new_zwl_pos] = RailEnvTransitionsEnum.right_turn_from_south.value

                    for c in range(mapping_only_pins_from_stations[succ][1] + 1, new_zwl_pos[1]):
                        assert zwl_grid[new_zwl_pos[0]][c] == 0
                        zwl_grid[new_zwl_pos[0]][c] = RailEnvTransitionsEnum.horizontal_straight.value
                    _handle_beyond_one_one(pos, env, mapping_only_pins_from_stations, zwl_grid_map, levels, reverse_levels)
            if pos in predecessors and len(predecessors[pos]) == 2:
                print(f"working on {pos} with predecessors {predecessors[pos]}")
                for num_pred, pred in enumerate(predecessors[pos]):
                    level_up_or_down = - _get_next_level(LEVEL, num_pred, pred, _get_succ_at_same_level(LEVEL, levels, pos, predecessors))
                    print(f"working on {pos} with predecessors {predecessors[pos]}: {pred}")

                    if pred not in open_cells:
                        print(f"{pos} <- {pred} already done")
                        continue
                    print(f"{pos} <- {pred}")
                    open_cells.discard(pos)

                    # one row above or below, same column:
                    new_zwl_pos = (mapping_only_pins_from_stations[pos][0] + level_up_or_down, mapping_only_pins_from_stations[pos][1])
                    if pred not in mapping_only_pins_from_stations:
                        print(f"add mapping {pred} -> {new_zwl_pos}")
                        # TODO why?
                        # assert zwl_grid[*new_zwl_pos] == 0
                        mapping_only_pins_from_stations[pred] = new_zwl_pos
                    else:
                        # happens if pred is a pin
                        pass

                    # TODO merge everything in handle_slips
                    trans = zwl_grid_map.grid[*mapping_only_pins_from_stations[pos]]
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
                    zwl_grid_map.grid[*mapping_only_pins_from_stations[pos]] = trans

                    # on pred, add curve: if +1, add E-N curve, if -1 add E-S curve
                    print(f"curve on {new_zwl_pos}")
                    if level_up_or_down == 1:
                        # up: E-N curve
                        zwl_grid_map.grid[*new_zwl_pos] = RailEnvTransitionsEnum.right_turn_from_north.value
                    elif level_up_or_down == -1:
                        # down: E-S curve
                        zwl_grid_map.grid[*new_zwl_pos] = RailEnvTransitionsEnum.right_turn_from_west.value

                    for c in range(mapping_only_pins_from_stations[pred][1] + 1, new_zwl_pos[1]):
                        assert zwl_grid[new_zwl_pos[0]][c] == 0
                        zwl_grid[new_zwl_pos[0]][c] = RailEnvTransitionsEnum.horizontal_straight.value

                    _handle_beyond_one_one(pos, env, mapping_only_pins_from_stations, zwl_grid_map, levels, reverse_levels)

    # # Find missing transitions going out/coming into the graph
    # # TODO why necessary? Why not handled above?
    for cell in successors.keys():
        # find missing neighbors
        _handle_beyond_one_one(cell, env, mapping_only_pins_from_stations, zwl_grid_map, levels, reverse_levels, random_allowed=True)

    # TODO document behaviour where this approach does not reflect the grid faithfully -> add sanity check, that the graph remains the same and fail/inform when the link map does not reflect the grid faithfully?
    mapping_merged = {**mapping_only_pins_from_stations, **mapping_from_to_station}
    content = {
        # ZWL grid
        "grid": zwl_grid,
        # env -> ZWL coordindates
        "mapping": [[[r, pos], list(v)] for (r, pos), v in mapping_merged.items()],
        "city_cells_bbox": city_1_cells_bbox,
        "levels": [[list(k), v] for k, v in levels.items()],
    }

    return content


def _handle_beyond_one_one(cell: tuple, env: RailEnv, mapping: dict[Any, Any], zwl_grid_map: GridTransitionMap[Any], levels: dict, reverse_levels: dict,
                           random_allowed: bool = False):
    # TODO cleanup: fix levels/mapping first and then same call _fix_zwl_cell_from_grid_neighbour_pairs  for all cases
    print(f"_handle_slips {cell}")
    if RailEnvTransitionsEnum.is_one_one(env.rail.grid[cell]):
        return

    level = levels[cell]
    pairs = env.rail.get_neighbor_pairs(cell)

    level_to_neighbor = defaultdict(set)
    for pair in pairs:
        for p in pair:
            level_to_neighbor[levels.get(p, None)].add(p)
    if None in level_to_neighbor and not random_allowed:
        assert len(level_to_neighbor[None]) == 1, level_to_neighbor

    # assert len(level_to_neighbor[level]) == 2, (cell, level_to_neighbor,level)
    # for n in level_to_neighbor[level]:
    #     assert n in mapping

    # for +0 transitions, nothing to do
    # for +1/-1 -> same neighbor
    # if one None: go one level further away from 0
    # if two Nones: assign randomly

    new_neighbors = {p for pair in pairs for p in pair if p not in mapping}
    above = (mapping[cell][0] - 1, mapping[cell][1])
    below = (mapping[cell][0] + 1, mapping[cell][1])

    print(f"  new_neighbors={new_neighbors} level_to_neighbor={level_to_neighbor}, level={level}")
    # if level != 0:
    #     assert len(new_neighbors) == 1, new_neighbors
    trans = zwl_grid_map.grid[*mapping[*cell]]

    if None in level_to_neighbor and len(level_to_neighbor[None]) == 1 and len(level_to_neighbor[level]) == 2 and len(level_to_neighbor[level - 1]) == 1:
        missing = list(level_to_neighbor[None])[0]
        level_to_neighbor.pop(None)
        target = level + 1
        level_to_neighbor[target].add(missing)
        _assign_level(missing, target, levels, reverse_levels)
    elif None in level_to_neighbor and len(level_to_neighbor[None]) == 1 and len(new_neighbors) == 1 and list(new_neighbors)[0] in levels:
        if level == 0:
            if len(level_to_neighbor[-1]) == 0:
                source = 1
                target = -1
            elif len(level_to_neighbor[1]) == 0:
                target = 1
                source = -1
            assert len(level_to_neighbor[source]) == 1
            missing = list(level_to_neighbor[None])[0]
            level_to_neighbor.pop(None)
            level_to_neighbor[target].add(missing)
            _assign_level(missing, target, levels, reverse_levels)
            print(f"fix {missing} {levels[missing]}")

        else:
            print("no fix")
    else:
        print("no fix")
    print(f"  new_neighbors={new_neighbors} level_to_neighbor={level_to_neighbor}, level={level} after fixing")

    print(f"  {RailEnvTransitionsEnum(env.rail.grid[*cell]).name}")
    cell_left = (cell[0], cell[1] - 1)
    cell_right = (cell[0], cell[1] + 1)
    cell_below = (cell[0] + 1, cell[1])
    me = mapping[cell]
    me_left = (me[0], me[1] - 1)
    me_right = (me[0], me[1] + 1)
    me_below = (me[0] + 1, me[1])
    me_above = (me[0] - 1, me[1])
    if len(new_neighbors) == 1 and None not in level_to_neighbor:
        new_neighbor = list(new_neighbors)[0]
        level_new_neighbor = levels[new_neighbor]

        if level_new_neighbor == level:
            assert len(level_to_neighbor[level]) == 2
            missing_map = cell_left if cell_right in mapping else cell_right
            assert missing_map not in mapping
            missing_link_map = me_right if me_right == mapping[new_neighbor] else me_left
            mapping[new_neighbor] = missing_link_map

            _fix_zwl_cell_from_grid_neighbour_pairs(cell, mapping, pairs, trans, zwl_grid_map)
            return
        elif level_new_neighbor == level + 1:
            # for slips
            # 0  - 1 -
            # | 1
            # results in the two cells mapped to the same cell: a split!
            mapping[new_neighbor] = me_below
            _fix_zwl_cell_from_grid_neighbour_pairs(cell, mapping, pairs, trans, zwl_grid_map)
            return
    elif len(new_neighbors) == 2 and None not in level_to_neighbor and len(level_to_neighbor[level]) == 2 and len(level_to_neighbor[level + 1]) == 1 and len(
            level_to_neighbor[level - 1]) == 1:
        neighbour_below_to_add = list(level_to_neighbor[level + 1])[0]
        neighbour_above_to_add = list(level_to_neighbor[level - 1])[0]
        mapping[neighbour_below_to_add] = me_below
        mapping[neighbour_above_to_add] = me_above
        _fix_zwl_cell_from_grid_neighbour_pairs(cell, mapping, pairs, trans, zwl_grid_map)
        return
    # elif len(new_neighbors) == 0 and None not in level_to_neighbor:
    #     _fix_zwl_cell_from_grid_neighbour_pairs(cell, env, mapping, pairs, trans, zwl_grid_map)
    #     return

    # new_neighbors={(15, 7), (15, 9)} level_to_neighbor=defaultdict(<class 'set'>, {0: {(16, 8), (14, 8)}, -1: {(15, 9)}, None: {(15, 7)}}), level=0
    #   new_neighbors={(15, 7), (15, 9)} level_to_neighbor=defaultdict(<class 'set'>, {0: {(16, 8), (14, 8)}, -1: {(15, 9)}, 1: {(15, 7)}}), level=0 after fixing

    assert cell not in new_neighbors
    chosen = None
    not_chosen = None

    if len(new_neighbors) == 2 and level == 0:
        print(new_neighbors)
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
            if not_chosen is not None:
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

                    elif not is_neighbor_cell(mapping[from_cell], mapping[cell]) and is_neighbor_cell(mapping[cell], mapping[to_cell]):
                        trans = zwl_grid_map.transitions.set_transition(trans, get_direction(replacement, mapping[cell]),
                                                                        get_direction(mapping[cell], mapping[to_cell]), 1)
                    else:
                        # TODO ignore and add warning instead?
                        raise
                elif len(new_neighbors) > 0:
                    # TODO add warning
                    print("ignoring")
                    raise
                else:
                    print(f"in grid, all neighbors mapped, but in zwl not everything neighbor on {cell}")
                    # TODO find out which level -> and fix -> maybe this is general -> keep track of levels in zwl for all cells, not only mapped ones?

    print(RailEnvTransitions().print(trans))
    if RailEnvTransitions().is_valid(trans):
        zwl_grid_map.grid[*mapping[*cell]] = trans
    else:
        orig = RailEnvTransitionsEnum(env.rail.grid[*cell])
        # mapped = RailEnvTransitionsEnum(zwl_grid_map.grid[*mapping[*cell]])
        print(cell)
        print(orig.name)
        print((new_neighbors, level_to_neighbor, level))
        # print(mapped)
        # TODO add warning instead?
        # raise


def _fix_zwl_cell_from_grid_neighbour_pairs(cell: tuple, mapping: dict[Any, Any], pairs: set[tuple[tuple[int, int], tuple[int, int]]],
                                            trans: ndarray[Any, dtype[floating[_64Bit]]] | Any, zwl_grid_map: GridTransitionMap[Any]):
    print(f"==== _fix_zwl_cell_from_grid_neighbour_pairs {cell}")
    orig = trans
    for from_cell, to_cell in pairs:
        assert is_neighbor_cell(mapping[from_cell], mapping[cell]) and is_neighbor_cell(mapping[cell], mapping[to_cell]), (from_cell, cell, to_cell,
                                                                                                                           mapping[from_cell], mapping[cell],
                                                                                                                           mapping[to_cell])
        print((from_cell, cell, to_cell, mapping[from_cell], mapping[cell], mapping[to_cell]), get_direction(from_cell, cell),
              get_direction(cell, to_cell), get_direction(mapping[from_cell], mapping[cell]),
              get_direction(mapping[cell], mapping[to_cell]))
        from_dir = get_direction(mapping[from_cell], mapping[cell])
        tod_dir = get_direction(mapping[cell], mapping[to_cell])
        trans_ = zwl_grid_map.transitions.set_transition(trans, from_dir, tod_dir, 1)
        trans_ = zwl_grid_map.transitions.set_transition(trans_, mirror(tod_dir), mirror(from_dir), 1)

        if RailEnvTransitions().is_valid(trans_):
            trans = trans_
        else:
            # TODO warning to frontend
            print(f" _fix_zwl_cell_from_grid_neighbour_pairs invalid")
    # print(RailEnvTransitions().print(trans))
    # if RailEnvTransitions().is_valid(trans):
    zwl_grid_map.grid[*mapping[*cell]] = trans
    print(f" _fix_zwl_cell_from_grid_neighbour_pairs invalid -> {RailEnvTransitionsEnum(orig).name} -> {RailEnvTransitionsEnum(trans).name}")
    # else:
    #     orig = RailEnvTransitionsEnum(env.rail.grid[*cell])
    #     # mapped = RailEnvTransitionsEnum(zwl_grid_map.grid[*mapping[*cell]])
    #     print(orig.name)
    #     # print(mapped)
    #     # TODO add warning instead?
    #     # raise


def _get_succ_at_same_level(LEVEL: int, levels: dict[tuple, int], pos: tuple, successors: dict[tuple, list[tuple]]):
    baseline_succ = None
    for succ in successors[pos]:
        if levels.get(succ, None) == LEVEL:
            baseline_succ = succ
            break
    return baseline_succ


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
