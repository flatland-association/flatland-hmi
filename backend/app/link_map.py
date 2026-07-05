from collections import defaultdict
from typing import Any, List, Dict, Optional, Tuple

import numpy as np
from numpy import dtype, floating, ndarray
from numpy._typing import _64Bit

from flatland.core.grid.grid4_utils import get_direction, is_neighbor_cell, mirror, direction_to_point
from flatland.core.transition_map import GridTransitionMap
from flatland.envs.grid.rail_env_grid import RailEnvTransitions
from flatland.envs.grid.rail_env_grid import RailEnvTransitionsEnum
from flatland.envs.grid4_generators_utils import connect_rail_in_grid_map
from flatland.envs.rail_env_shortest_paths import get_k_shortest_paths
from flatland.envs.rail_trainrun_data_structures import Waypoint
from flatland.envs.stations_links import Fibre, Gate, Link, Pin, StationsLinks

_DIRECTION_NAMES = {0: "N", 1: "E", 2: "S", 3: "W"}
_DIRECTION_CHARS = {v: k for k, v in _DIRECTION_NAMES.items()}


def _assign_level(cell: Tuple, level: int, levels: Dict[Tuple, int], reverse_levels: Dict[int, set]) -> None:
    """Record `cell`'s ZWL level in both `levels` and `reverse_levels`, unless it has already been assigned one."""
    if cell in levels:
        # TODO does error in some cases
        # assert levels[cell] == level, (cell, levels[cell], level)
        return
    levels[cell] = level
    reverse_levels[level].add(cell)


def _get_next_level(LEVEL: int, num_succ: int, succ: Tuple, baseline_succ: Optional[Tuple]) -> int:
    """Decide the level offset (-1, 0, or +1) a branch at a switch should move to, based on whether `succ` is the baseline branch and its clockwise position among its siblings."""
    # N.B. left/right is preserved only for 0->1 / 0->-1, for other levels it's always away.
    # N.B. if we have isolated loops, this approach does not well defined:
    #         |--1--------------------|
    #         |  |--1-------------|   |
    #  0 -----|--|--0-------------|---|----
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


def _map_levels_to_link_map(levels: dict[tuple, int], mapping_only_pins_from_stations: GridTransitionMap[Any], open_cells: dict[int, set[tuple]],
                            predecessors: dict[tuple, list[tuple]], reverse_levels: set[tuple[Any]], successors: dict[tuple, list[tuple]],
                            zwl_grid: ndarray[Any, dtype[Any]], zwl_grid_map: dict[Any, Any]):
    """Walk the level-assigned graph level by level, writing the corresponding curve/straight transitions into `zwl_grid`/`zwl_grid_map` and extending `mapping_only_pins_from_stations` with the newly placed cells."""
    # Based on levels, map to link map
    # TODO fix -2/2 etc.why does it fail?
    for LEVEL in [0, 1, -1]:  # , 2 - 2]:
        if LEVEL not in reverse_levels:
            continue

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
                                assert RailEnvTransitions().is_valid(trans)
                                zwl_grid_map.grid[(row, c)] = trans
                                index = int((i / len_mapped) * len(stretch))
                                # TODO safe?
                                if stretch[index] not in mapping_only_pins_from_stations:
                                    mapping_only_pins_from_stations[stretch[index]] = (row, c)

                        else:
                            pass
                            # TODO when does it happen - ignore?

        # treat degree 2 out of LEVEL
        for pos in reverse_levels[LEVEL]:
            if pos in successors and len(successors[pos]) == 2:
                for num_succ, succ in enumerate(successors[pos]):
                    # TODO bad code smell - levels should already be assigned!
                    level_up_or_down = _get_next_level(LEVEL, num_succ, succ, _get_succ_at_same_level(LEVEL, levels, pos, successors))

                    if succ not in open_cells:
                        continue
                    open_cells.discard(pos)

                    # one row above or below, same column:
                    new_zwl_pos = (mapping_only_pins_from_stations[pos][0] + level_up_or_down, mapping_only_pins_from_stations[pos][1])
                    if succ not in mapping_only_pins_from_stations:
                        assert zwl_grid[*new_zwl_pos] == 0
                        mapping_only_pins_from_stations[succ] = new_zwl_pos
                    else:
                        # happens if pred is a pin
                        pass

                    trans = zwl_grid_map.grid[*mapping_only_pins_from_stations[pos]]

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
                    if level_up_or_down == 1:
                        # up: S-E curve
                        zwl_grid_map.grid[*new_zwl_pos] = RailEnvTransitionsEnum.right_turn_from_east.value
                    elif level_up_or_down == -1:
                        # down: N-E curve
                        zwl_grid_map.grid[*new_zwl_pos] = RailEnvTransitionsEnum.right_turn_from_south.value

                    for c in range(mapping_only_pins_from_stations[succ][1] + 1, new_zwl_pos[1]):
                        assert zwl_grid[new_zwl_pos[0]][c] == 0
                        zwl_grid[new_zwl_pos[0]][c] = RailEnvTransitionsEnum.horizontal_straight.value
            if pos in predecessors and len(predecessors[pos]) == 2:
                for num_pred, pred in enumerate(predecessors[pos]):
                    level_up_or_down = - _get_next_level(LEVEL, num_pred, pred, _get_succ_at_same_level(LEVEL, levels, pos, predecessors))

                    if pred not in open_cells:
                        continue
                    open_cells.discard(pos)

                    # one row above or below, same column:
                    new_zwl_pos = (mapping_only_pins_from_stations[pos][0] + level_up_or_down, mapping_only_pins_from_stations[pos][1])
                    if pred not in mapping_only_pins_from_stations:
                        # TODO why?
                        # assert zwl_grid[*new_zwl_pos] == 0
                        mapping_only_pins_from_stations[pred] = new_zwl_pos
                    else:
                        # happens if pred is a pin
                        pass

                    # TODO merge everything in handle_slips
                    trans = zwl_grid_map.grid[*mapping_only_pins_from_stations[pos]]
                    # on pos, add transition: if +1, add N-E trans, if -1 add S-E trans
                    if level_up_or_down == 1:
                        # from up to right:
                        trans = zwl_grid_map.transitions.set_transition(trans, 0, 1, 1)
                        trans = zwl_grid_map.transitions.set_transition(trans, 3, 2, 1)
                    else:
                        # from down to right:
                        trans = zwl_grid_map.transitions.set_transition(trans, 2, 1, 1)
                        trans = zwl_grid_map.transitions.set_transition(trans, 3, 0, 1)
                    zwl_grid_map.grid[*mapping_only_pins_from_stations[pos]] = trans

                    # on pred, add curve: if +1, add E-N curve, if -1 add E-S curve
                    if level_up_or_down == 1:
                        # up: E-N curve
                        zwl_grid_map.grid[*new_zwl_pos] = RailEnvTransitionsEnum.right_turn_from_north.value
                    elif level_up_or_down == -1:
                        # down: E-S curve
                        zwl_grid_map.grid[*new_zwl_pos] = RailEnvTransitionsEnum.right_turn_from_west.value

                    for c in range(mapping_only_pins_from_stations[pred][1] + 1, new_zwl_pos[1]):
                        assert zwl_grid[new_zwl_pos[0]][c] == 0
                        zwl_grid[new_zwl_pos[0]][c] = RailEnvTransitionsEnum.horizontal_straight.value


def _assign_levels_for_context(levels: dict[tuple, int], predecessors: dict[tuple, list[tuple]], rail: GridTransitionMap, reverse_levels: set[tuple[Any]],
                               successors: dict[tuple, list[tuple]]):
    """Extend level assignment to the neighbor cells just outside the gate-to-gate path graph (e.g. switches/crossings bordering the fibre), inferring their direction and level from the already-known predecessors/successors of each cell."""
    # assign levels for context (outside of gate-gate paths)
    for cell in successors.keys():
        assert set(predecessors[cell]).isdisjoint(successors[cell])
        if len(predecessors[cell]) == 0 or len(successors[cell]) == 0:
            continue

        level = levels[cell]

        pairs = rail.get_neighbor_pairs(cell)

        new_neighbors = {p for pair in pairs for p in pair if p not in successors}
        all_neighbors = {p for pair in pairs for p in pair}

        # assuming cells between stations in fibres are never passed in opcelling directions
        known_incoming_neighbors = {pair[0] for pair in pairs if pair[1] in successors[cell]}.union(predecessors[cell])
        known_outgoing_neighbors = {pair[1] for pair in pairs if pair[0] in predecessors[cell]}.union(successors[cell])
        assert known_incoming_neighbors.isdisjoint(known_outgoing_neighbors)
        assert known_incoming_neighbors.union(known_outgoing_neighbors).union(new_neighbors) == all_neighbors, (
            known_incoming_neighbors.union(known_outgoing_neighbors).union(new_neighbors), all_neighbors)

        fixed_incoming_new_neighbors = set()
        fixed_outgoing_new_neighbors = set()
        cell_successors = set()
        cell_predecessors = set()

        for pair in pairs:
            from_cell, to_cell = pair
            if from_cell in new_neighbors and to_cell in known_outgoing_neighbors:
                assert from_cell not in fixed_outgoing_new_neighbors
                fixed_incoming_new_neighbors.add(from_cell)
            elif to_cell in new_neighbors and from_cell in known_incoming_neighbors:
                assert to_cell not in fixed_incoming_new_neighbors
                fixed_outgoing_new_neighbors.add(to_cell)

            if from_cell in known_incoming_neighbors or to_cell in known_outgoing_neighbors:
                dir_entering = direction_to_point(from_cell, cell)
                dir_exiting = direction_to_point(cell, to_cell)
                # TODO sorting acutally wrong: we should use the direction change from dir_entering and lookup the direction we exit by in the transition map
                cell_predecessors.add((from_cell, dir_entering))
                cell_successors.add((to_cell, dir_exiting))
        assert new_neighbors == fixed_incoming_new_neighbors.union(fixed_outgoing_new_neighbors)

        cell_predecessors = [t[0] for t in sorted(set(cell_predecessors), key=lambda t: t[1])]
        cell_successors = [t[0] for t in sorted(set(cell_successors), key=lambda t: t[1])]
        assert 0 < len(cell_predecessors) <= 2, cell_predecessors
        assert 0 < len(cell_successors) <= 2, cell_successors

        if level != 0:
            for n in new_neighbors:
                if level > 0:
                    _assign_level(n, level + 1, levels, reverse_levels)
                elif level < 0:
                    _assign_level(n, level - 1, levels, reverse_levels)

        # cover case one new neighbor first
        else:
            for num_succ, succ in enumerate(cell_successors):
                if succ not in new_neighbors:
                    continue
                level_up_or_down = _get_next_level(level, num_succ, succ, _get_succ_at_same_level(level, levels, cell, {cell: cell_successors}))

                _assign_level(succ, level + level_up_or_down, levels, reverse_levels)

            for num_pred, pred in enumerate(cell_predecessors):
                if pred not in new_neighbors:
                    continue
                level_up_or_down = - _get_next_level(level, num_pred, pred, _get_succ_at_same_level(level, levels, cell, {cell: cell_predecessors}))

                _assign_level(pred, level + level_up_or_down, levels, reverse_levels)


def _assign_levels_in_station_to_station_graph(fibre: Fibre, from_gate: Gate | None, from_pin_index: int | None,
                                               mapping_only_pins_from_stations: GridTransitionMap[Any], predecessors: dict[tuple, list[tuple]],
                                               successors: dict[tuple, list[tuple]], to_gate: Gate | None, to_pin_index: int | None) -> tuple[
    dict[tuple, int], dict[int, set[tuple]], set[tuple]]:
    """Assign a ZWL level to every cell in the station-to-station path graph, starting from the fibre (level 0) and its gate pins, then iteratively propagate levels along degree-2 branches; returns the level map, the still-unmapped cells, and the per-level cell index."""
    # cells in the graph without a mapping assigned yet:
    open_cells = set(successors.keys())
    # for each cell, which level does it have: switches still at same level but next cells have level +1/-1
    levels: dict[tuple, int] = {}
    # for each level, which cells are at the level
    reverse_levels: dict[int, set[tuple]] = defaultdict(set)

    # define level 0:
    for cell in (tuple(c) for c in fibre.edges):
        open_cells.discard(cell)
        _assign_level(cell, 0, levels, reverse_levels)

    # add levels to from and to pin (might not be covered by paths)
    baseline_row = mapping_only_pins_from_stations[tuple(fibre.edges[0])][0]
    pin: Pin
    for level, pin in zip(range(-from_pin_index, len(from_gate.pins) - from_pin_index + 1), from_gate.pins.values()):
        level = mapping_only_pins_from_stations[tuple(pin.node)][0] - baseline_row
        _assign_level(tuple(pin.node), level, levels, reverse_levels)
    for level, pin in zip(range(-to_pin_index, len(to_gate.pins) - to_pin_index + 1), to_gate.pins.values()):
        level = mapping_only_pins_from_stations[tuple(pin.node)][0] - baseline_row
        _assign_level(tuple(pin.node), level, levels, reverse_levels)

    # Iteratively, assign levels to graph (all paths between chosen link's gates)
    for LEVEL in [0, 1, -1, 2 - 2]:
        if LEVEL not in reverse_levels:
            continue
        reverse_levels_open = defaultdict(set)

        for pos in reverse_levels[LEVEL]:
            if pos in successors and len(successors[pos]) == 2:
                for num_succ, succ in enumerate(successors[pos]):
                    level_up_or_down = _get_next_level(LEVEL, num_succ, succ, _get_succ_at_same_level(LEVEL, levels, pos, successors))

                    if succ not in open_cells:
                        continue

                    _assign_level(succ, levels[pos] + level_up_or_down, levels, reverse_levels_open)

            if pos in predecessors and len(predecessors[pos]) == 2:
                for num_pred, pred in enumerate(predecessors[pos]):
                    level_up_or_down = - _get_next_level(LEVEL, num_pred, pred, _get_succ_at_same_level(LEVEL, levels, pos, predecessors))

                    if pred not in open_cells:
                        continue
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
    return levels, open_cells, reverse_levels


def _init_zwl_grid_from_fibre(link: Link, fibre: Fibre, rail: GridTransitionMap, stations_links: StationsLinks, from_dir_char: str, from_gate: Gate | None,
                              from_station: str,
                              to_dir_char: str, to_gate: Gate | None, to_station: str) -> tuple[
    dict[Any, Any], GridTransitionMap[Any], ndarray[Any, dtype[Any]], dict[Any, Any]]:
    """Build the initial ZWL grid by placing the rotated bounding boxes of the two stations side by side and connecting their pins along the fibre; returns the full station-cell mapping, the pin-only mapping, the raw grid, and its `GridTransitionMap` wrapper."""

    start = tuple(fibre.edges[0])
    end = tuple(fibre.edges[-1])

    from_facing: int = _DIRECTION_CHARS[from_dir_char]
    to_facing: int = _DIRECTION_CHARS[to_dir_char]

    zwl_grid = np.zeros(shape=(rail.grid.shape[0], rail.grid.shape[1] + 50), dtype=int)
    city_1_bb, city_1_cells_bbox, mapping1 = _extract_city_rotated(from_station, from_facing, stations_links, rail, 1)
    city_2_bb, city_2_cells_bbox, mapping2 = _extract_city_rotated(to_station, to_facing, stations_links, rail, 3)

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
    x_offset_2 = city_1_bb.shape[1] + len(fibre.edges) - 2
    if end_y < straight_y:
        y_offset_2 = straight_y - end_y
    zwl_grid[y_offset_2:city_2_bb.shape[0] + y_offset_2, x_offset_2:city_2_bb.shape[1] + x_offset_2] = city_2_bb

    zwl_grid = zwl_grid[:max(city_1_bb.shape[0] + y_offset_1, city_2_bb.shape[0] + y_offset_2), :x_offset_2 + city_2_bb.shape[1]]

    mapping2 = {k: (r + y_offset_2, pos + x_offset_2) for k, (r, pos) in mapping2.items()}

    # mapping so far contains all cells in the two station bb
    mapping_from_to_station = {**mapping1, **mapping2}

    _from_to_gate_pin_nodes = {
        tuple(pin.node)
        for gate in [from_gate, to_gate]
        if gate
        for pin in gate.pins.values()
    }
    _other_station_pin_nodes = {
                                   tuple(pin.node)
                                   for station_name in [from_station, to_station]
                                   for gate in stations_links.stations[station_name].gates.values()
                                   for pin in gate.pins.values()
                               } - _from_to_gate_pin_nodes
    mapping_only_pins_from_stations = {
        k: v
        for k, v in mapping_from_to_station.items()
        if k not in _other_station_pin_nodes
    }

    zwl_grid_map = GridTransitionMap(height=zwl_grid.shape[0], width=zwl_grid.shape[1], transitions=RailEnvTransitions(), grid=zwl_grid)
    path = connect_rail_in_grid_map(
        grid_map=zwl_grid_map,
        rail_trans=RailEnvTransitions(),
        start=mapping_only_pins_from_stations[start],
        end=mapping_only_pins_from_stations[end],
    )
    assert path[0] == mapping_only_pins_from_stations[start]
    assert path[-1] == mapping_only_pins_from_stations[end]
    assert len(fibre.edges) == len(path)
    for i, cell in enumerate(path):
        mapping_only_pins_from_stations[tuple(fibre.edges[i])] = cell

    return mapping_from_to_station, mapping_only_pins_from_stations, zwl_grid, zwl_grid_map


def _build_adjacency(all_paths: List[List[Waypoint]], forward: bool, label: str) -> Dict[tuple, List[tuple]]:
    """Build a cell -> ordered list of at most two neighbor cells (successors if `forward`, predecessors otherwise) from a set of paths, sorted clockwise by the direction change at each cell."""
    # cell -> List[tuple[tuple,int]]
    raw: dict[tuple, set[tuple[tuple, int]]] = {}
    for path in all_paths:
        for wp, wp_after in zip(path, path[1:]):
            raw.setdefault(wp_after.position, set())
            raw.setdefault(wp.position, set())
            # +1 means to the right forward
            # -1 means to the left forward
            direction_change = (wp_after.direction - wp.direction) % 4
            assert direction_change in {0, 1, 3}
            if direction_change == 3:
                direction_change = -1
            if forward:
                raw.setdefault(wp.position, set()).add((wp_after.position, direction_change))
            else:
                raw.setdefault(wp_after.position, set()).add((wp.position, direction_change))

    # cell -> List[tuple[tuple]] covering all paths between the two gates from left to right; ordered clock-wise
    adjacency: Dict[tuple, List[tuple]] = {cell: [t[0] for t in sorted(neighbors, key=lambda t: t[1])] for cell, neighbors in raw.items()}
    for k, v in adjacency.items():
        res = []
        for i in v:
            if i not in res:
                res.append(i)
        adjacency[k] = res
        assert len(res) <= 2, res
    return adjacency


def _extract_station_to_station_graph(link: Link, rail: GridTransitionMap, stations_links: StationsLinks) -> tuple[
    dict[tuple, list[tuple]], dict[tuple, list[tuple]]]:
    """Find all paths between the two gates of `link` and derive the successor/predecessor adjacency graph over their cells."""
    all_paths = _find_all_paths_between_stations(link, stations_links, rail)
    successors = _build_adjacency(all_paths, forward=True, label="successors")
    predecessors = _build_adjacency(all_paths, forward=False, label="predecessors")
    return predecessors, successors


def _handle_beyond_one_one(cell: Tuple, rail: GridTransitionMap, mapping: Dict[Tuple, Tuple], zwl_grid_map: GridTransitionMap,
                           levels: Dict[Tuple, int], random_allowed: bool = True) -> None:
    """Complete the ZWL mapping for a cell that is not a simple 1-in-1-out crossing (e.g. a switch or slip) by mapping its still-unmapped grid neighbors to the free cell(s) above/below/at the same row, based on their assigned levels."""
    if RailEnvTransitionsEnum.is_one_one(rail.grid[cell]):
        return

    level = levels[cell]
    pairs = rail.get_neighbor_pairs(cell)

    level_to_neighbor = defaultdict(set)
    for pair in pairs:
        for p in pair:
            level_to_neighbor[levels.get(p, None)].add(p)
    if None in level_to_neighbor and not random_allowed:
        assert len(level_to_neighbor[None]) == 1, level_to_neighbor

    new_neighbors = {p for pair in pairs for p in pair if p not in mapping}
    assert cell not in new_neighbors
    above = (mapping[cell][0] - 1, mapping[cell][1])
    below = (mapping[cell][0] + 1, mapping[cell][1])

    trans = zwl_grid_map.grid[*mapping[*cell]]

    cell_left = (cell[0], cell[1] - 1)
    cell_right = (cell[0], cell[1] + 1)
    me = mapping[cell]
    me_left = (me[0], me[1] - 1)
    me_right = (me[0], me[1] + 1)
    me_below = (me[0] + 1, me[1])
    me_above = (me[0] - 1, me[1])
    if len(new_neighbors) == 1:
        new_neighbor = list(new_neighbors)[0]
        level_new_neighbor = levels[new_neighbor]

        if None not in level_to_neighbor and level_new_neighbor == level:
            assert len(level_to_neighbor[level]) == 2
            missing_map = cell_left if cell_right in mapping else cell_right
            assert missing_map not in mapping
            missing_link_map = me_right if me_right == mapping[new_neighbor] else me_left
            mapping[new_neighbor] = missing_link_map

        elif None not in level_to_neighbor and level_new_neighbor == level + 1:
            # for slips
            # 0  - 1 -
            # | 1
            # results in the two cells mapped to the same cell: a split!
            mapping[new_neighbor] = me_below
        else:
            if zwl_grid_map.grid[*above] == 0:
                chosen = above
            elif zwl_grid_map.grid[*below] == 0:
                chosen = below
            else:
                # TODO add warning instead?
                raise
            assert zwl_grid_map.grid[*chosen] == 0
            n = list(new_neighbors)[0]
            assert n not in mapping
            mapping[n] = chosen
    elif len(new_neighbors) == 2 and None not in level_to_neighbor and len(level_to_neighbor[level]) == 2 and len(level_to_neighbor[level + 1]) == 1 and len(
            level_to_neighbor[level - 1]) == 1:
        neighbour_below_to_add = list(level_to_neighbor[level + 1])[0]
        neighbour_above_to_add = list(level_to_neighbor[level - 1])[0]
        mapping[neighbour_below_to_add] = me_below
        mapping[neighbour_above_to_add] = me_above
    elif len(new_neighbors) == 2 and level == 0:
        assert zwl_grid_map.grid[*above] == 0
        assert zwl_grid_map.grid[*below] == 0

        # randomly assign neighbors to above and below
        for n, mapped in zip(new_neighbors, [above, below]):
            assert n not in mapping
            mapping[n] = mapped

    _fix_zwl_cell_from_grid_neighbour_pairs(cell, mapping, pairs, trans, zwl_grid_map)


def _fix_zwl_cell_from_grid_neighbour_pairs(cell: tuple, mapping: dict[Any, Any], pairs: set[tuple[tuple[int, int], tuple[int, int]]],
                                            trans: ndarray[Any, dtype[floating[_64Bit]]] | Any, zwl_grid_map: GridTransitionMap[Any]):
    """Derive and set the ZWL transition bits for `cell` from the direction pairs of its already-mapped grid neighbors, applying the result only if the resulting transition bitmask is valid."""
    for from_cell, to_cell in pairs:
        if not (is_neighbor_cell(mapping[from_cell], mapping[cell]) and is_neighbor_cell(mapping[cell], mapping[to_cell])):
            # TODO highlight incomplete cases in frontend
            continue
        assert is_neighbor_cell(mapping[from_cell], mapping[cell]) and is_neighbor_cell(mapping[cell], mapping[to_cell]), (from_cell, cell, to_cell,
                                                                                                                           mapping[from_cell], mapping[cell],
                                                                                                                           mapping[to_cell])
        from_dir = get_direction(mapping[from_cell], mapping[cell])
        tod_dir = get_direction(mapping[cell], mapping[to_cell])
        trans = zwl_grid_map.transitions.set_transition(trans, from_dir, tod_dir, 1)
        trans = zwl_grid_map.transitions.set_transition(trans, mirror(tod_dir), mirror(from_dir), 1)

    if RailEnvTransitions().is_valid(trans):
        zwl_grid_map.grid[*mapping[*cell]] = trans


def _get_succ_at_same_level(LEVEL: int, levels: dict[tuple, int], pos: tuple, successors: dict[tuple, list[tuple]]) -> Optional[tuple]:
    """Return whichever successor of `pos` is already assigned to `LEVEL` (the baseline branch), or `None` if none is."""
    baseline_succ = None
    for succ in successors[pos]:
        if levels.get(succ, None) == LEVEL:
            baseline_succ = succ
            break
    return baseline_succ


def _find_all_paths_between_stations(link: Link, stations_links: StationsLinks, rail: GridTransitionMap) -> List[List[Waypoint]]:
    """Find up to 10 shortest paths between every pin of the link's from-gate and every pin of its to-gate, searching the rail grid with all station cells (except pins) masked out."""
    from_station, from_dir_char, _ = link.from_pin.split(".")
    to_station, to_dir_char, _ = link.to_pin.split(".")
    from_facing_int: int = _DIRECTION_CHARS[from_dir_char]
    to_facing_int: int = _DIRECTION_CHARS[to_dir_char]

    grid_without_stations = rail.grid.copy()
    pin_cells = [pin.node for station in stations_links.stations.values() for gate in station.gates.values() for pin in gate.pins.values()]
    for station in stations_links.stations.values():
        for cell in station.edges:
            if cell in pin_cells:
                continue
            grid_without_stations[cell[0]][cell[1]] = 0
    grid_map_without_stations = GridTransitionMap(height=grid_without_stations.shape[0], width=grid_without_stations.shape[1], transitions=RailEnvTransitions(),
                                                  grid=grid_without_stations)

    from_pins: List[Tuple] = [(p.node, from_facing_int) for p in stations_links.stations[from_station].gates[from_dir_char].pins.values()]
    to_pins: List[Tuple] = [(p.node, to_facing_int) for p in stations_links.stations[to_station].gates[to_dir_char].pins.values()]

    all_paths: List[List[Waypoint]] = []
    for (source_position, source_direction) in from_pins:
        for target_position, target_direction in to_pins:
            paths = get_k_shortest_paths(None, rail=grid_map_without_stations,
                                         source_position=source_position,
                                         source_direction=source_direction,
                                         target_position=target_position, k=10)
            all_paths.extend(paths)
    return all_paths


def _extract_city_rotated(city: str, city_orientation: int, stations_links: StationsLinks, rail: GridTransitionMap, target_facing: int = 1) -> Tuple[
    ndarray[Any, dtype[floating[_64Bit]]], Dict[str, Any], Dict[Tuple, Tuple]]:
    """Extract the bounding-box grid of `city`'s cells, rotate it (and its transitions) so its facing matches `target_facing`, and return the rotated grid together with its bounding box and a cell-to-rotated-cell coordinate mapping."""
    num_rot = target_facing - city_orientation
    num_rot %= 4

    all_city_cells = list(stations_links.stations[city].edges)
    city_cells_bbox = {
        "min_row": min(cell[0] for cell in all_city_cells),
        "max_row": max(cell[0] for cell in all_city_cells),
        "min_col": min(cell[1] for cell in all_city_cells),
        "max_col": max(cell[1] for cell in all_city_cells),
    }

    city_bb = rail.grid[city_cells_bbox["min_row"]:city_cells_bbox["max_row"] + 1, city_cells_bbox["min_col"]:city_cells_bbox["max_col"] + 1].copy()
    height, width = city_bb.shape

    city_bb = np.rot90(city_bb, -1 * num_rot)

    for r in range(city_bb.shape[0]):
        for c in range(city_bb.shape[1]):
            city_bb[r, c] = RailEnvTransitions().rotate_transition(city_bb[r, c], rotation=90 * num_rot)

    def rotate(r, c, max_r):
        """Rotate a single (row, col) coordinate 90 degrees clockwise within a grid of height `max_r + 1`."""
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


def extract_link_map(stations_links: StationsLinks, link: Link, fibre: Fibre, rail: GridTransitionMap) -> dict:
    """
    Extract a link map (an extract of a rail grid linearized along a link fibre between to stations) and a partial mapping from grid cells to link map cells.

    Steps:
    1. `_init_zwl_grid_from_fibre` - place the two stations' grids and connect the fibre
    2. `_extract_station_to_station_graph` - build the successor/predecessor graph between gates
    3. `_assign_levels_in_station_to_station_graph` - assign levels along the gate-to-gate graph
    4. `_assign_levels_for_context` - assign levels to cells bordering the graph
    5. `_map_levels_to_link_map` - write levels' transitions into the link map grid
    6. `_handle_beyond_one_one` - resolve remaining switches/slips per cell

    The current approach has several limitations:
    - L/R and straight/deviating are not always preserved (e.g. the straight crossing might be transformed to a deviating if the linearization is along the deviation)
    - intertwined fork/joins from the same level will not work as they are mapped to the same next level
    - some elements cannot be linearized along any transition (e.g. there is no single rail element when a single slip is linearized); we'd have to "make space" to map
    - some elements are not joined correctly, although they exist (e.g. symmetric switches)
    - more than two levels left/right of the fibre are not supported.


    Parameters
    ----------
    stations_links
    link
    fibre
    rail

    Returns
    -------

    """
    from_pin: str = link.from_pin
    to_pin: str = link.to_pin
    from_station: str
    from_dir_char: str
    from_track_str: str
    from_station, from_dir_char, from_track_str = from_pin.split(".")
    to_station: str
    to_dir_char: str
    to_track_str: str
    to_station, to_dir_char, to_track_str = to_pin.split(".")
    from_gate: Optional[Gate] = stations_links.stations[from_station].gates.get(from_dir_char)
    from_pin_index: Optional[int] = int(from_track_str) if from_gate else None

    to_gate: Optional[Gate] = stations_links.stations[to_station].gates.get(to_dir_char)
    to_pin_index: Optional[int] = int(to_track_str) if to_gate else None

    mapping_from_to_station, mapping_only_pins_from_stations, zwl_grid, zwl_grid_map = _init_zwl_grid_from_fibre(link, fibre, rail, stations_links,
                                                                                                                 from_dir_char, from_gate,
                                                                                                                 from_station, to_dir_char, to_gate, to_station)
    predecessors, successors = _extract_station_to_station_graph(link, rail, stations_links)

    levels, open_cells, reverse_levels = _assign_levels_in_station_to_station_graph(fibre, from_gate, from_pin_index, mapping_only_pins_from_stations,
                                                                                    predecessors, successors, to_gate, to_pin_index)

    assert set(predecessors.keys()) == set(successors.keys())

    _assign_levels_for_context(levels, predecessors, rail, reverse_levels, successors)

    _map_levels_to_link_map(levels, mapping_only_pins_from_stations, open_cells, predecessors, reverse_levels, successors, zwl_grid, zwl_grid_map)

    # Find missing transitions going out/coming into the graph
    for cell in successors.keys():
        # try to fix transitions
        _handle_beyond_one_one(cell, rail, mapping_only_pins_from_stations, zwl_grid_map, levels, random_allowed=True)

    mapping_merged = {**mapping_only_pins_from_stations, **mapping_from_to_station}
    content = {
        # link map grid
        "grid": zwl_grid,
        # env coordinates -> link map coordindates
        "mapping": [[[r, pos], list(v)] for (r, pos), v in mapping_merged.items()],
        "levels": [[list(k), v] for k, v in levels.items()],
    }

    return content
