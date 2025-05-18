from fastapi import APIRouter
from app.env import interactive_env

router = APIRouter()

@router.get("/transitions")
def get_transitions():
  return interactive_env.env.rail.grid.tolist()

@router.get("/agents")
def get_map():  
  return [{
    'position': None if agent.position is None else tuple(int(c) for c in agent.position),
    'direction': agent.direction,
    'moving': agent.moving,
    'speed_counter': agent.speed_counter,
    'target': None if agent.target is None else tuple(int(c) for c in agent.target),
  } for agent in interactive_env.env.agents]

@router.post("/step")
def step_env(actions: dict = {}):
  _, _, done, info, actions = interactive_env.step(actions)
  return {
    "info": info,
    "done": done,
    "actions": actions,
    "steps": interactive_env.env._elapsed_steps,
    "max_steps": interactive_env.env._max_episode_steps,
  }

@router.post("/reset")
def reset_env():
  _, info = interactive_env.reset()
  return {
    "info": info,
    "done": {
      "__all__": False
    },
    "steps": interactive_env.env._elapsed_steps,
  }