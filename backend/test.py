from app.env import InteractiveEnv

# Import hack4rail environment generator providing a static environment
from app.scenario.hack4rail import Hack4RailEnvGenerator

# Import the DeadLockAvoidancePolicy from the policies module
from app.policy.deadlock_avoidance_policy import DeadLockAvoidancePolicy

# Import the RandomPolicy from the policies module
from app.policy.random_policy import RandomPolicy

# Create a random agent policy
random_policy = RandomPolicy()





# Initialize the interactive environment with env and policy
interactive_env = InteractiveEnv(generator=Hack4RailEnvGenerator(), baseline_policy=DeadLockAvoidancePolicy(), plan_policies=[DeadLockAvoidancePolicy(), RandomPolicy()])

for _ in range(100):
    interactive_env.step(0)
    print(", ".join([str(step.get("0")["position"]) for step in interactive_env.history_env.steps]))