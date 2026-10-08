"""The transport port: a byte stream between the host and the instrument.

The upper layers depend on this interface only. A serial port, an in-memory
pipe or any other channel can carry the protocol by implementing it.
"""

from __future__ import annotations

from typing import Protocol


class Transport(Protocol):
    """Bidirectional byte stream."""

    def read(self, max_bytes: int, timeout: float | None) -> bytes:
        """Read up to ``max_bytes`` bytes.

        The call returns as soon as at least one byte is available. Otherwise it
        waits for ``timeout`` seconds; ``None`` waits without limit and zero
        does not wait.

        Returns:
            The bytes read, or an empty value if the timeout expired.

        Raises:
            ValueError: If ``max_bytes`` is not positive.
            TransportClosedError: If the transport is closed.
            TransportError: If the underlying channel failed.
        """

    def write(self, data: bytes) -> None:
        """Send all of ``data``.

        Raises:
            TransportClosedError: If the transport is closed.
            TransportError: If the underlying channel failed.
        """

    def close(self) -> None:
        """Release the channel. Closing a closed transport does nothing."""
