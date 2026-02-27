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
    interactive_env = InteractiveEnv(env_map[env_id](), policy_map[policy_id]())
    interactive_env.reset()
    while not interactive_env.done.get("__all__", False):
        interactive_env.step()
    print(interactive_env.env._elapsed_steps)
