from fastapi import APIRouter
from app.env import interactive_env
from app.scenario.hack4rail import Hack4RailEnvGenerator

router = APIRouter()


@router.get("/transitions")
def get_transitions():
    return interactive_env.env.rail.grid.tolist()


@router.get("/agents")
def get_map():
    return [
        {
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
        for agent in interactive_env.env.agents
    ]


@router.post("/step")
def step_env(actions: dict = {}):
    _, _, done, info, actions = interactive_env.step(actions)
    return _step_to_dict(done, info, actions)

def _step_to_dict(done, info, actions):
    return {
        "info": info,
        "done": done,
        "actions": {
            a: {"name": action.name, "value": action.value}
            for a, action in actions.items()
        },
        "steps": interactive_env.env._elapsed_steps,
        "max_steps": interactive_env.env._max_episode_steps,
    }

@router.get("/steps")
def step_env_all():
    steps = []
    for _, _, done, info, actions in interactive_env.all_steps():
        steps.append(_step_to_dict(done, info, actions))
    return steps


@router.post("/reset")
def reset_env():
    _, info = interactive_env.reset()
    return {
        "info": info,
        "done": {"__all__": False},
        "steps": interactive_env.env._elapsed_steps,
    }

@router.get("/timetable", response_model=Hack4RailEnvGenerator)
def get_timetable():
    return interactive_env.generator    