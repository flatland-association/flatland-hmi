import logging
from typing import Optional

from flatland.core.env_observation_builder import DummyObservationBuilder
from flatland.env_generation.env_generator import env_generator
from flatland.envs.rail_env import RailEnv
from flatland.envs.rail_env_action import RailEnvActions
from flatland_baselines.deadlock_avoidance_heuristic.observation.full_env_observation import FullEnvObservation
from flatland_baselines.deadlock_avoidance_heuristic.policy.deadlock_avoidance_policy import DeadLockAvoidancePolicy
from tests.trajectories.test_policy_runner import RandomPolicy


class InteractiveEnv:
    def __init__(self, env: RailEnv, policy):
        self.env = env
        self.policy = policy
        self.obs = None
        self.info = None
        self.done = {}

    def reset(self):
        self.obs, self.info = self.env.reset()
        self.done = {}
        return self.obs, self.info

    def step(self, explicit_actions=None):
        if explicit_actions is None:
            explicit_actions = {}
        if self.done.get("__all__", False):
            raise Exception("Environment done, call reset() to start a new episode")
        actions = self.policy.act_many(self.env.get_agent_handles(), self.obs)
        actions.update(
            {
                a: RailEnvActions.from_value(action)
                for a, action in explicit_actions.items()
            }
        )
        self.obs, self.rewards, self.done, self.info = self.env.step(actions)
        return self.obs, self.rewards, self.done, self.info, actions


env_map = {
    'generated-0': {
        'factory': lambda **kwargs: env_generator(**kwargs)[0],
        'description': 'Generated environment 30 x 30, 7 agents',
    },
    'generated-1': {
        'factory': lambda **kwargs: env_generator(x_dim=50, y_dim=50, n_agents=10, **kwargs)[0],
        'description': 'Generated environment 50 x 50, 10 agents',
    },
}
policy_map = {
    'policy-0': {
        'factory': RandomPolicy,
        'description': 'Random Policy',
        'obs_builder_factory': DummyObservationBuilder
    },
    'policy-1': {
        'factory': DeadLockAvoidancePolicy,
        'description': 'Deadlock Avoidance Heuristic',
        'obs_builder_factory': FullEnvObservation
    },
}


def reset_global_interactive_env(env_id, policy_id) -> tuple:
    global interactive_env
    interactive_env = InteractiveEnv(env_map[env_id]['factory'](obs_builder_object=policy_map[policy_id]['obs_builder_factory']()), policy_map[policy_id]['factory']())
    return interactive_env.reset()


def get_global_interactive_env() -> Optional[InteractiveEnv]:
    global interactive_env
    return interactive_env


interactive_env: InteractiveEnv = None
try:
    reset_global_interactive_env("generated-0", "policy-0")
except Exception as e:
    logging.getLogger(__name__).error("Failed to initialise default environment: %s", e)
