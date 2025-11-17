from flatland.env_generation.env_generator import env_generator
from flatland.envs.rail_env import RailEnv
from flatland.envs.rail_env_action import RailEnvActions


class InteractiveEnv:
    def __init__(self, env: RailEnv, policy):
        self.env = env
        self.policy = policy
        self.reset()

    def reset(self):
        self.obs, self.info = self.env.reset()
        self.done = {}
        return self.obs, self.info

    def step(self, explicit_actions={}):
        if self.done.get("__all__", False):
            raise Exception("Environment done, call reset() to start a new episode")
        actions = self.policy.act_many(self.obs)
        actions.update(
            {
                a: RailEnvActions.from_value(action)
                for a, action in explicit_actions.items()
            }
        )
        self.obs, self.rewards, self.done, self.info = self.env.step(actions)
        return self.obs, self.rewards, self.done, self.info, actions


# Import hack4rail environment generator providing a static environment
#from .scenario.hack4rail import create_hack4rail_env

# Create the hack4rail environment
#env = create_hack4rail_env()
env = env_generator()[0]

# Import the RandomPolicy from the policies module
from .policy.random_policy import RandomPolicy

# Create a random agent policy
random_policy = RandomPolicy()

# Import the DeadLockAvoidancePolicy from the policies module
from .policy.deadlock_avoidance_policy import DeadLockAvoidancePolicy

# Create a deadlock avoidance policy
deadlock_avoidance_policy = DeadLockAvoidancePolicy(env=env)

# Initialize the interactive environment with env and policy
# TODO fix dla with new flatland version
interactive_env = InteractiveEnv(env, random_policy)
