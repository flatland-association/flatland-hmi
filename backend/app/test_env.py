import pytest

from app.env import InteractiveEnv, env_map, policy_map


@pytest.mark.parametrize(
    "env_id,policy_id,n",
    [(env_id, policy_id, n)
     for env_id in ["generated-0", "generated-1"]
     for policy_id in ["policy-0", "policy-1"]
     for n in range(10)]
)
def test_loop(env_id, policy_id, n):
    # generated-0/generated-1 draw their seed from OS entropy when unseeded, so pin it here:
    # otherwise generation is non-deterministic and can occasionally produce a disconnected
    # layout that fails DeadLockAvoidancePolicy's path-finding, flaky only in full-suite runs.
    interactive_env = InteractiveEnv(
        env_map[env_id]["factory"](obs_builder_object=policy_map[policy_id]["obs_builder_factory"](), seed=n),
        policy_map[policy_id]["factory"](),
    )
    interactive_env.reset()
    while not interactive_env.done.get("__all__", False):
        interactive_env.step()
    print(interactive_env.env._elapsed_steps)
