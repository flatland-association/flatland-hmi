import random
from flatland.envs.rail_env import RailEnv
from flatland.envs.rail_generators import sparse_rail_generator
from flatland.envs.line_generators import sparse_line_generator
from flatland.envs.observations import TreeObsForRailEnv
from flatland.envs.predictions import ShortestPathPredictorForRailEnv

class RandomAgent:
    def act(self, _obs):
        return random.randint(0, 4)

class InteractiveEnv:
    def __init__(self, env, policy):
        self.env = env
        self.policy = policy
        self.reset()

    def reset(self):
        self.obs, self.info = self.env.reset()
        self.done = {}
        return self.obs, self.info

    def step(self, explicit_actions = {}):
        if self.done.get("__all__", False):
            raise Exception("Environment done, call reset() to start a new episode")
        actions = {a: self.policy.act(self.obs[a]) for a in range(self.env.get_num_agents())}
        actions.update(explicit_actions)
        self.obs, self.rewards, self.done, self.info = self.env.step(actions)
        return self.obs, self.rewards, self.done, self.info, actions

# Create a Flatland environment
env = RailEnv(
  width=32,
  height=32,
  rail_generator=sparse_rail_generator(
      max_num_cities=5,
      grid_mode=False,
      max_rails_between_cities=2,
      max_rail_pairs_in_city=2
  ),
  line_generator=sparse_line_generator(),
  number_of_agents=7,
  obs_builder_object=TreeObsForRailEnv(max_depth=3, predictor=ShortestPathPredictorForRailEnv())
)

# Create a random agent policy
policy = RandomAgent()

# Initialize the interactive environment with env and policy
interactive_env = InteractiveEnv(env, policy)