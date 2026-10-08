"""The byte-stream port and its adapters.

``Transport`` is the interface the upper layers depend on. ``MemoryTransport``
connects two sides inside one process and ``SerialTransport`` talks to a
serial port.
"""

from __future__ import annotations

from s3_power_profiler.transport.base import Transport
from s3_power_profiler.transport.memory import MemoryTransport, memory_pair
from s3_power_profiler.transport.serial import SerialTransport

__all__ = ["MemoryTransport", "SerialTransport", "Transport", "memory_pair"]
