"""In-memory transport: two connected ends that carry bytes between them.

It replaces a cable in tests and in simulation. The ends are safe to use from
two threads. A single thread can also drive both sides by installing a pump on
the reading end, as :func:`s3_power_profiler.sim.connect_simulator` does.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from s3_power_profiler.errors import TransportClosedError


class _Pipe:
    """One direction of the connection."""

    def __init__(self) -> None:
        self.data = bytearray()
        self.condition = threading.Condition()
        self.closed = False


class MemoryTransport:
    """One end of an in-memory connection. Create both with :func:`memory_pair`."""

    def __init__(self, inbound: _Pipe, outbound: _Pipe) -> None:
        self._inbound = inbound
        self._outbound = outbound
        self._pump: Callable[[], None] | None = None
        self._closed = False

    @property
    def closed(self) -> bool:
        """True after this end was closed."""
        return self._closed

    def set_pump(self, pump: Callable[[], None] | None) -> None:
        """Install the function that lets the other side run.

        When a read finds nothing to return, it calls the pump once before
        waiting. In a single-threaded program the pump runs the peer, which
        consumes what was written to it and produces its answer, so the read
        can return it. Pass None to remove the pump.
        """
        self._pump = pump

    def read(self, max_bytes: int, timeout: float | None) -> bytes:
        """Read up to ``max_bytes`` bytes sent by the other end.

        Returns:
            The bytes read, or an empty value if the timeout expired.

        Raises:
            ValueError: If ``max_bytes`` is not positive.
            TransportClosedError: If this end is closed, or the other end is
                closed and everything it sent was already read.
        """
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self._ensure_open()
        pipe = self._inbound
        if self._pump is not None and not self._has_data():
            self._pump()
        with pipe.condition:
            if not pipe.data and not pipe.closed and (timeout is None or timeout > 0):
                pipe.condition.wait_for(lambda: bool(pipe.data) or pipe.closed, timeout)
            if pipe.data:
                chunk = bytes(pipe.data[:max_bytes])
                del pipe.data[:max_bytes]
                return chunk
            if pipe.closed:
                raise TransportClosedError("the other end closed the connection")
            return b""

    def write(self, data: bytes) -> None:
        """Send ``data`` to the other end.

        Raises:
            TransportClosedError: If either end is closed.
        """
        self._ensure_open()
        pipe = self._outbound
        with pipe.condition:
            if pipe.closed:
                raise TransportClosedError("the other end closed the connection")
            pipe.data += data
            pipe.condition.notify_all()

    def close(self) -> None:
        """Close this end. The other end can still read what was already sent."""
        if self._closed:
            return
        self._closed = True
        for pipe in (self._inbound, self._outbound):
            with pipe.condition:
                pipe.closed = True
                pipe.condition.notify_all()

    def _ensure_open(self) -> None:
        if self._closed:
            raise TransportClosedError("the transport is closed")

    def _has_data(self) -> bool:
        with self._inbound.condition:
            return bool(self._inbound.data)


def memory_pair() -> tuple[MemoryTransport, MemoryTransport]:
    """Create two connected ends: what one writes, the other reads."""
    forward = _Pipe()
    backward = _Pipe()
    return MemoryTransport(backward, forward), MemoryTransport(forward, backward)
