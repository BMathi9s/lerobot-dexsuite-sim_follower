#!/usr/bin/env python
from dataclasses import dataclass, field
from ..config import RobotConfig

@RobotConfig.register_subclass("so101_websim_follower")
@dataclass
class SO101WebSimFollowerConfig(RobotConfig):
    # where to stream joint targets
    ws_url: str = "ws://127.0.0.1:8765"

    # joint names must match your teleop action keys "<name>.pos"
    joint_names: list[str] = field(default_factory=lambda: [
        "shoulder_pan",
        "shoulder_lift",
        "elbow_flex",
        "wrist_flex",
        "wrist_roll",
        "gripper",
    ])

    # optional safety clamp (same spirit as so101 follower)
    max_relative_target: float | dict[str, float] | None = None

    # limits (optional; leave None to skip clamping)
    joint_min: list[float] | None = None
    joint_max: list[float] | None = None
