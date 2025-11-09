#!/usr/bin/env python
from __future__ import annotations
import asyncio, json, time
from functools import cached_property
from typing import Any, Optional

import websockets

from ..robot import Robot
from ..utils import ensure_safe_goal_position
from .config_so101_websim_follower import SO101WebSimFollowerConfig

class SO101WebSimFollower(Robot):
    """
    Follower that streams joint positions to a simulator over WebSocket.
    Joint key format matches teleop: '<joint>.pos'.
    """
    config_class = SO101WebSimFollowerConfig
    name = "so101_websim_follower"

    def __init__(self, config: SO101WebSimFollowerConfig):
        super().__init__(config)
        self.config = config
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._seq = 0
        self._last_send_log = 0.0
        self._last_obs: dict[str, Any] = {f"{jn}.pos": 0.0 for jn in self.config.joint_names}
        self._last_obs["timestamp"] = time.time()

    # ---------- features ----------
    @cached_property
    def action_features(self) -> dict[str, type]:
        return {f"{jn}.pos": float for jn in self.config.joint_names}

    @cached_property
    def observation_features(self) -> dict[str, type]:
        return {**{f"{jn}.pos": float for jn in self.config.joint_names}, "timestamp": float}

    # ---------- connection ----------
    @property
    def is_connected(self) -> bool:
        return self._ws is not None

    def connect(self, calibrate: bool = False) -> None:
        if self.is_connected:
            raise RuntimeError(f"{self} already connected")
        # small retry window so you can start teleop first, then the server
        for attempt in range(10):
            try:
                self._run(self._async_connect(), timeout=2.0)
                print("[websim follower] connected")
                break
            except Exception as e:
                print(f"[websim follower] connect failed ({attempt+1}/10): {e}")
                time.sleep(0.5)
        if not self.is_connected:
            raise RuntimeError("websim follower: cannot connect to simulator")

    def disconnect(self) -> None:
        if not self.is_connected:
            raise RuntimeError(f"{self} is not connected")
        self._run(self._async_disconnect())
        print("[websim follower] disconnected")

    # ---------- I/O ----------
    def get_observation(self) -> dict[str, Any]:
        msg = self._run(self._async_try_recv(), timeout=0.0)
        if msg:
            try:
                data = json.loads(msg)
                if data.get("type") == "state":
                    if "names" in data and "joint_pos" in data:
                        name_to_val = dict(zip(data["names"], data["joint_pos"]))
                    elif "joint_pos" in data and isinstance(data["joint_pos"], list):
                        name_to_val = dict(zip(self.config.joint_names, data["joint_pos"]))
                    else:
                        name_to_val = {}
                    for jn, v in name_to_val.items():
                        key = f"{jn}.pos"
                        if key in self._last_obs:
                            self._last_obs[key] = float(v)
                    self._last_obs["timestamp"] = float(data.get("timestamp", time.time()))
            except Exception:
                pass
        return dict(self._last_obs)

    def send_action(self, action: dict[str, Any]) -> dict[str, Any]:
        # Extract goal positions keyed like '<joint>.pos'
        goal_pos = {k.removesuffix(".pos"): float(v) for k, v in action.items() if k.endswith(".pos")}

        # Guard: if empty, surface it loudly (helps catch key-name mismatches)
        if not goal_pos:
            print("[websim follower] WARN: outgoing goal_pos is empty — check action keys end with '.pos'")
            # still proceed with last obs (no-op move)

        # Optional relative safety
        if self.config.max_relative_target is not None:
            present = {k.removesuffix(".pos"): self._last_obs[k] for k in self._last_obs if k.endswith(".pos")}
            goal_present = {jn: (goal_pos.get(jn, present[jn]), present[jn]) for jn in self.config.joint_names}
            goal_pos = ensure_safe_goal_position(goal_present, self.config.max_relative_target)

        # Optional absolute clamp
        if self.config.joint_min and self.config.joint_max:
            clamped = {}
            for i, jn in enumerate(self.config.joint_names):
                lo = self.config.joint_min[i]
                hi = self.config.joint_max[i]
                val = goal_pos.get(jn, self._last_obs[f"{jn}.pos"])
                clamped[jn] = min(max(val, lo), hi)
            goal_pos = clamped

        self._seq += 1
        payload = {
            "type": "cmd",
            "seq": self._seq,
            "mode": "joint_position",
            "names": self.config.joint_names,
            "target": [goal_pos.get(jn, self._last_obs[f"{jn}.pos"]) for jn in self.config.joint_names],
            "timestamp": time.time(),
        }

        # debug print: first 3 joints (rate-limited)
        now = time.time()
        if now - self._last_send_log > 1.0 or self._seq < 5:
            print("[websim follower ->cmd]", ", ".join(f"{v:+.3f}" for v in payload["target"][:3]), "…")
            self._last_send_log = now

        try:
            self._run(self._async_send(payload))
        except Exception as e:
            print(f"[websim follower] send failed: {e}")

        # optimistic update
        for i, jn in enumerate(self.config.joint_names):
            self._last_obs[f"{jn}.pos"] = payload["target"][i]
        self._last_obs["timestamp"] = payload["timestamp"]
        return {f"{jn}.pos": payload["target"][i] for i, jn in enumerate(self.config.joint_names)}

    # ---------- tiny asyncio helpers ----------
    def _run(self, coro, timeout: Optional[float] = None):
        loop = asyncio.get_event_loop()
        task = coro if timeout is None else asyncio.wait_for(coro, timeout=timeout)
        try:
            return loop.run_until_complete(task)
        except asyncio.TimeoutError:
            return None

    async def _async_connect(self):
        self._ws = await websockets.connect(
            self.config.ws_url,
            max_size=2**20,
            ping_interval=None,   # disable client pings
        )

    async def _async_disconnect(self):
        try:
            if self._ws:
                await self._ws.close()
        finally:
            self._ws = None

    async def _async_send(self, payload: dict):
        if not self._ws:
            raise RuntimeError("websocket not connected")
        try:
            await self._ws.send(json.dumps(payload))
        except websockets.ConnectionClosed:
            self._ws = None
            raise

    async def _async_try_recv(self) -> Optional[str]:
        if not self._ws:
            return None
        try:
            return await asyncio.wait_for(self._ws.recv(), timeout=0.0)
        except asyncio.TimeoutError:
            return None
        except websockets.ConnectionClosed:
            self._ws = None
            return None

    # ----- required abstract hooks (no-ops for a simulator) -----
    @property
    def is_calibrated(self) -> bool:
        return True

    def calibrate(self) -> None:
        return

    def configure(self) -> None:
        return
