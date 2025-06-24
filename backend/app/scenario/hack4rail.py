import numpy as np
from flatland.envs.timetable_utils import Line, Timetable
from flatland.envs.rail_grid_transition_map import RailGridTransitionMap
from flatland.core.grid.rail_env_grid import RailEnvTransitions

from .static import create_static_env


def create_hack4rail_env():
    """
    Create a static Flatland environment for the Hack4Rail competition.
    The environment is defined by a specific grid, line, and timetable.
    """

    width = 30
    height = 2

    map = RailGridTransitionMap(
        width=width, height=height, transitions=RailEnvTransitions()
    )
    map.grid = np.array(
        [
            [
                4,
                1025,
                1025,
                4608,
                0,
                0,
                0,
                0,
                0,
                0,
                16386,
                5633,
                17411,
                1025,
                1025,
                1025,
                5633,
                1025,
                17411,
                1025,
                1025,
                4608,
                0,
                0,
                0,
                0,
                16386,
                1025,
                1025,
                256,
            ],
            [
                4,
                1025,
                1025,
                1097,
                1025,
                1025,
                1025,
                1025,
                1025,
                1025,
                3089,
                1097,
                3089,
                1025,
                1025,
                1025,
                1097,
                1025,
                3089,
                1025,
                1025,
                1097,
                1025,
                1025,
                1025,
                1025,
                3089,
                1025,
                1025,
                256,
            ],
        ]
    )

    return create_static_env(
        width=width,
        height=height,
        map=map,
        line=Line(
            agent_positions=[
                [(1, 2)],
                [(0, 2), (1, 14)],
                [(1, 27)],
                [(0, 27), (1, 14)],
            ],
            agent_directions=[[1], [1, 1], [3], [3, 3]],
            agent_targets=[(1, 27), (0, 27), (0, 2), (1, 2)],
            agent_speeds=[1.0, 0.8, 1.0, 0.8],
        ),
        timetable=Timetable(
            earliest_departures=[[4, None], [0, 21, None], [4, None], [0, 24, None]],
            latest_arrivals=[[None, 29], [None, 19, 43], [None, 29], [None, 22, 43]],
            max_episode_steps=120,
        ),
    )
