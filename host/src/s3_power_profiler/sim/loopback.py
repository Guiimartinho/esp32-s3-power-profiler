"""Wiring of a simulator to a client inside one thread.

This is the composition point of the simulation: it is the only module of the
package that joins the simulator to a concrete transport.
"""

from __future__ import annotations

from s3_power_profiler.sim.simulator import Simulator, SimulatorConfig
from s3_power_profiler.transport.memory import MemoryTransport, memory_pair


def connect_simulator(
    config: SimulatorConfig | None = None, *, boot: bool = True
) -> tuple[MemoryTransport, Simulator]:
    """Create a simulator and return the host end of its connection.

    The simulator runs cooperatively in the calling thread. Whenever the host
    end has nothing to read, the simulator answers the commands written so far
    and, while streaming, sends one more frame. No thread and no sleep are
    involved, so a run is fully repeatable.

    Args:
        config: Behavior of the instrument, or None for the defaults.
        boot: Run the start-up sequence, so the simulator is ready for commands.

    Returns:
        The transport for a client, and the simulator for inspection and for
        injecting faults.
    """
    host_end, device_end = memory_pair()
    simulator = Simulator(device_end, config)
    if boot:
        simulator.boot()
    host_end.set_pump(simulator.step)
    return host_end, simulator
