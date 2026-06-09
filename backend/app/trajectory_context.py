import json
import os
import uuid
from pathlib import Path
from typing import NamedTuple, Optional, Dict

from fastapi import HTTPException

from app.env import policy_map, env_map
from flatland.envs.observations import FullEnvObservation
from flatland.trajectories.policy_runner import PolicyRunner
from flatland.trajectories.trajectories import Trajectory

DATA_DIR = os.getenv("HMI_DATA_DIR", "./hmi_data_dir")

# TODO approach is not support scaling of the backend as trajectory is not persisted on every step()
trajectory_context_map: Dict[str, PolicyRunner] = {}


class TrajectoryContext(NamedTuple):
    trajectory: Trajectory
    meta: dict
    policy_runner: Optional[PolicyRunner]

    def to_dict(self) -> Dict:
        return {
            "ep_id": self.trajectory.ep_id,
            "policy_id": self.meta.get("policy_id"),
            "env_id": self.meta.get("env_id"),
            "elapsed_steps": self.policy_runner.env._elapsed_steps,
            "done": self.policy_runner.env.dones.get("__all__", False),
        }

    @classmethod
    def create(cls, env_id: str, policy_id: str):
        ep_id = str(uuid.uuid4())
        data_dir = Path(DATA_DIR) / ep_id
        data_dir.mkdir(exist_ok=True, parents=True)
        env = env_map.get(env_id)["factory"](obs_builder_object=policy_map[policy_id]["obs_builder_factory"]())
        t = Trajectory.create_empty(data_dir, ep_id=ep_id, env=env)
        t_runner = PolicyRunner(
            policy=policy_map.get(policy_id)["factory"](),
            trajectory=t,
        )
        meta = {"policy_id": policy_id, "env_id": env_id}
        (data_dir / "meta.json").write_text(
            json.dumps(meta)
        )
        ctx = TrajectoryContext(trajectory=t, meta=meta, policy_runner=t_runner, )
        trajectory_context_map[ep_id] = ctx
        return ctx

    def fork(self):
        fork_id = str(uuid.uuid4())
        base = Path(DATA_DIR).resolve()
        fork_path = (base / fork_id).resolve()
        policy_runner = self.policy_runner
        policy_runner.trajectory.persist()

        fork = policy_runner.trajectory.fork(data_dir=fork_path, start_step=policy_runner.env._elapsed_steps, ep_id=fork_id)
        with (fork_path / "meta.json").open("w") as f:
            json.dump(self.meta, f)
        fork_policy_runner = PolicyRunner(
            policy=policy_map.get(self.meta["policy_id"])["factory"](),
            trajectory=fork,
        )
        ctx = TrajectoryContext(trajectory=fork, meta=json.load((fork_path / "meta.json").open("r")), policy_runner=fork_policy_runner, )
        trajectory_context_map[fork_id] = ctx
        return ctx

    @classmethod
    def resolve(cls, trajectory_id: str) -> "TrajectoryContext":
        if trajectory_id in trajectory_context_map:
            return trajectory_context_map[trajectory_id]
        base = Path(DATA_DIR).resolve()
        p = (base / trajectory_id).resolve()
        if not p.exists():
            raise HTTPException(status_code=404, detail="Trajectory not found")
        if not str(p).startswith(str(base)):
            raise HTTPException(status_code=400, detail="Invalid trajectory ID")
        meta_path = p / "meta.json"
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        t = Trajectory.load_existing(data_dir=p, ep_id=trajectory_id)
        policy_id = meta.get("policy_id")
        policy_runner = PolicyRunner(
            policy=policy_map.get(policy_id)["factory"](),
            trajectory=t,
        )
        t = Trajectory.load_existing(Path(DATA_DIR), trajectory_id)
        ctx = cls(trajectory=t, meta=meta, policy_runner=policy_runner)
        trajectory_context_map[t.ep_id] = ctx
        return ctx

    def update_policy(self, policy_id: str):
        meta = self.meta
        meta_path = self.trajectory.data_dir / "meta.json"
        policy_runner = self.policy_runner
        effective_policy_id = policy_id or meta.get("policy_id")
        meta["policy_id"] = effective_policy_id
        policy = policy_map.get(effective_policy_id)["factory"]()
        with meta_path.open("w") as f:
            json.dump(meta, f)

        # TODO: dla is not correctly initialized
        if policy_id is not None:
            # TODO use factory
            policy_runner.change_policy(policy, FullEnvObservation())

    def get_env(self):
        if self.policy_runner is not None:
            return self.policy_runner.env
        return self.trajectory.load_env(obs_builder=policy_map[self.meta["policy_id"]]["obs_builder_factory"]())
