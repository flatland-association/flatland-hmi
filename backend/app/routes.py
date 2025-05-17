from fastapi import APIRouter
from app.env import interactive_env

router = APIRouter()

@router.get("/map")
def get_map():
  return interactive_env.env.rail.grid.tolist()

@router.get("/agents")
def get_map():  
  return {i: {
    'position': None if agent.position is None else tuple(int(c) for c in agent.position),
    'direction': agent.direction,
    'moving': agent.moving,
    'speed_counter': agent.speed_counter
  } for i, agent in enumerate(interactive_env.env.agents)}

@router.post("/step")
def step_env(actions: dict = {}):
  _, _, done, info, actions = interactive_env.step(actions)
  return {
    "info": info,
    "done": done,
    "actions": actions
  }

@router.post("/reset")
def reset_env():
  _, info = interactive_env.reset()
  return info