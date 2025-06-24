from flatland.envs.rail_env_action import RailEnvActions


class InteractiveEnv:
    def __init__(self, env, policy):
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


# import random env generator
from .scenario.random import create_random_env

# create a random Flatland environment
env = create_random_env(width=32, height=32)


# Import the RandomPolicy from the policies module
from .policy.random_policy import RandomPolicy

# Create a random agent policy
random_policy = RandomPolicy()

# Import the DeadLockAvoidancePolicy from the policies module
from .policy.deadlock_avoidance_policy import DeadLockAvoidancePolicy

# Create a deadlock avoidance policy
deadlock_avoidance_policy = DeadLockAvoidancePolicy(env=env)

# Initialize the interactive environment with env and policy
interactive_env = InteractiveEnv(env, deadlock_avoidance_policy)
