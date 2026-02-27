from flatland.env_generation.env_generator import env_generator
from flatland.envs.rail_env import RailEnv
from flatland.envs.rail_env_action import RailEnvActions
from flatland_baselines.deadlock_avoidance_heuristic.observation.full_env_observation import FullEnvObservation
from flatland_baselines.deadlock_avoidance_heuristic.policy.deadlock_avoidance_policy import DeadLockAvoidancePolicy
# TODO use random policy from baselines instead
from tests.trajectories.test_policy_runner import RandomPolicy


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
    'generated-0': env_generator(obs_builder_object=FullEnvObservation())[0],
    'generated-1': env_generator(x_dim=50, y_dim=50, n_agents=10, obs_builder_object=FullEnvObservation())[0],
}
policy_map = {
    'policy-0': RandomPolicy(),
    'policy-1': DeadLockAvoidancePolicy(),
}


def reset_global_interactive_env(env_id, policy_id):
    global interactive_env
    interactive_env = InteractiveEnv(env_map[env_id], policy_map[policy_id])
    return interactive_env

def get_global_interactive_env():
    global interactive_env
    return interactive_env

interactive_env = reset_global_interactive_env("generated-0", "policy-0")
