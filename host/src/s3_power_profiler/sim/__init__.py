"""A deterministic fake instrument for tests and offline work."""

from __future__ import annotations

from s3_power_profiler.sim.loopback import connect_simulator
from s3_power_profiler.sim.simulator import Simulator, SimulatorConfig

__all__ = ["Simulator", "SimulatorConfig", "connect_simulator"]
